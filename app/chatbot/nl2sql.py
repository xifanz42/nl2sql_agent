import logging
import os
import re
import time
from collections import Counter
from typing import Literal

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

from app import PROJECT_ROOT
from app.chatbot.session import (
    SessionStore,
    SessionStoreUnavailable,
    build_session_store,
    normalize_session_id,
)
from app.core.database import DataBase
from app.core.document_processor import DocumentProcessor
from app.core.generation import parse_generation
from app.core.knowledge_base import KnowledgeBase

# from transformers import AutoTokenizer, AutoModel, pipeline # local call llm
from app.core.llm import (
    SiliconFlowLLM,
    TokenUsage,
    reset_request_usage,
    set_request_usage,
)  # api call llm
from app.core.schema_profile import profile_database, render_profile
from app.models.chat import ChatResult, ChatSession, Turn

logger = logging.getLogger(__name__)

# Short-term compaction (PR1b). Char counts are a deterministic proxy for tokens.
MAX_HISTORY_TURNS = 12
MAX_HISTORY_CHARS = 24_000
KEEP_RECENT_TURNS = 8
MAX_SUMMARY_CHARS = 2_000

# Analysis prompt guards: the user still receives the full result object.
MAX_ANALYSIS_ROWS = 300
MAX_ANALYSIS_CHARS = 20_000


class NL2SQLChatbot:
    def __init__(
        self,
        documents_dir: str | None = None,
        embedding_dim: int = 384,
        session_store: SessionStore | None = None,
    ):
        """
        Initialize the NL2SQL Chatbot with document processing and database capabilities

        Args:
            documents_dir: Directory containing knowledge documents
            embedding_dim: Dimension of embedding vectors
            session_store: Per-conversation store; Redis by default, SQLite fallback
        """
        documents_dir = documents_dir or str(PROJECT_ROOT / "data")
        # # Initialize the LLM
        # self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        # self.model = AutoModel.from_pretrained(model_name)
        # self.nlp_pipeline = pipeline("text2text-generation", model=model_name, max_length=1024)
        self.model_engine = SiliconFlowLLM()

        # Database connection
        self.db = DataBase()

        # Load schema info
        self.schema_info = self.db.get_schema_as_dict()
        # Compact, structural schema for the generation prompt
        self.schema_profile = render_profile(profile_database(self.db))

        # Document processing
        self.doc_processor = DocumentProcessor(embedding_dim=embedding_dim)
        self.knowledge_base = KnowledgeBase(embedding_dim=embedding_dim)

        # Try to load cached knowledge base
        start_time = time.time()
        load_result = self.knowledge_base.load()
        print("knowledge_base load_result: ", load_result)

        if "No cache" in load_result:
            # Process documents if no cache
            self._process_documents(documents_dir)
            # Save knowledge base for future use
            self.knowledge_base.save()
        else:
            print(f"Loaded knowledge base in {time.time() - start_time:.2f}s")

        # Per-conversation short-term state (Fix 16)
        self.sessions = session_store or build_session_store()

        # Query optimization
        self.common_terms = Counter()

    def _process_documents(self, documents_dir):
        """Process all documents in the specified directory"""
        if not os.path.exists(documents_dir):
            print(f"Documents directory not found: {documents_dir}")
            return

        for filename in os.listdir(documents_dir):
            file_path = os.path.join(documents_dir, filename)
            if os.path.isfile(file_path):
                print(f"Processing {filename}...")
                result = self.knowledge_base.add_document(file_path, self.doc_processor)
                print(result)

    def _update_query_statistics(self, query):
        """Update statistics about common query terms for optimization"""
        # Simple tokenization
        terms = re.findall(r"\b\w+\b", query.lower())
        self.common_terms.update(terms)

    def _retrieve_relevant_knowledge(self, query):
        """Retrieve relevant information from knowledge base"""
        # Track query patterns to improve future retrievals
        self._update_query_statistics(query)

        # Use MMR for diverse results
        results = self.knowledge_base.retrieve_with_mmr(
            query, self.doc_processor, top_k=5, diversity=0.35
        )

        # results = self.knowledge_base.retrieve_relevant(query, self.doc_processor, top_k=3)

        if not results:
            return "No relevant information found."

        # Group results by source to improve context coherence
        source_groups = {}
        for result in results:
            source = result["metadata"]["source"]
            if source not in source_groups:
                source_groups[source] = []
            source_groups[source].append(result)

        relevant_text = ""

        # Add results, grouped by source
        for source, items in source_groups.items():
            relevant_text += f"[Document: {source}]\n"

            # Sort items by their original index to maintain document flow
            items.sort(key=lambda x: x["metadata"]["index"])

            for item in items:
                relevant_text += f"{item['text']}\n\n"

        return relevant_text

    def retrieve_knowledge(self, query: str) -> str:
        """Public accessor for the retrieval step.

        Exposed so evaluation baselines (``direct+rag``) reuse the agent's real
        retriever instead of duplicating it: improve RAG here and every system
        under eval picks it up.
        """
        return self._retrieve_relevant_knowledge(query)

    def render_prompt(
        self,
        *,
        knowledge: str = "",
        history: str = "",
        summary: str = "",
        is_followup: bool = False,
    ) -> str:
        """Render the agent's system prompt from its parts.

        Deliberately split out of ``_prepare_prompt`` and free of any LLM call or
        retrieval, so an evaluation baseline can share the *identical* template
        while still being a single model call. Routing a baseline through
        ``_prepare_prompt`` would make it inherit the agent's preprocessing (the
        follow-up detector is one extra model call), which imports agent
        architecture into the baseline and understates the difference under test.
        """
        # Keep the single-turn eval prompt byte-identical: only add the summary
        # block when a summary actually exists.
        summary_block = f"        之前的对话摘要：{summary}" if summary else ""

        return f"""
        基于数据table schema：{self.schema_profile}

        和知识库相关内容：{knowledge}
{summary_block}
        以及历史会话记录：{history}
        {"这是基于上一轮对话的一个follow-up。" if is_followup else ""}

        生成合法的SQL SELECT语句，要求：
        1. 先判断是否需要拒绝、引导用户提问或者提问用户获取信息
        2. 如果有足够信息，生成合法的SQL SELECT语句
        3. 返回查询结果

        如果问题涉及的指标、字段、维度或时间范围在当前数据中不存在，或请求超出只读查询范围，respond with: "无法回答: [specific reason]"
        指标/字段不存在时才拒绝；指标/字段存在但缺少时间范围、过滤条件或有歧义时，仍请求澄清。
        如果模糊判断需要更多信息, respond with: "请提供具体信息: [specific question]"
        如果用户需要引导，respond with: "引导提问: [specific instruction]"
        如果已经有足够信息来生成sql, respond with: "SQL_QUERY: [SQL_QUERY]"
        """

    def _prepare_prompt(self, user_query, session: ChatSession):
        """Prepare a prompt for the language model"""
        # Retrieve relevant knowledge
        start_time = time.time()
        relevant_knowledge = self._retrieve_relevant_knowledge(user_query)
        retrieval_time = time.time() - start_time
        print(f"Knowledge retrieval time: {retrieval_time:.2f}s")

        # Format conversation history
        history_text = ""

        for turn in session.history[-3:]:  # Last 3 turns for context
            user_text = turn.user or "Unknown User Input"
            system_text = turn.system or "No System Response"
            history_text += f"User: {user_text}\nSystem: {system_text}\n"

        # Detect if this is a follow-up question
        is_followup = self._detect_followup_question(user_query, session)

        return self.render_prompt(
            knowledge=relevant_knowledge,
            history=history_text,
            summary=session.summary,
            is_followup=is_followup,
        )

    def _detect_followup_question(self, query, session: ChatSession):
        """Detect if the current question is a follow-up to previous ones using LLM."""

        # A follow-up presupposes an earlier turn, so with no history the answer is
        # False by definition -- and asking a 7B helper to classify a question it
        # has no context for is not merely wasteful, it is unreliable: measured
        # against the eval set it answers "True" for 73/90 single-turn questions.
        if not session.history:
            return False

        # Construct conversation context from the last few exchanges
        conversation_context = ""
        for turn in session.history[-3:]:  # Last 3 turns for context
            user_text = turn.user or "Unknown User Input"
            system_text = turn.system or "No System Response"
            conversation_context += f"User: {user_text}\nSystem: {system_text}\n"

        # Construct prompt to ask LLM
        prompt = f"""
        Given the conversation history below:

        {conversation_context}

        User's current query: {query}

        Is the user's current query a follow-up to the previous questions? Respond with 'yes' or 'no'.
        """

        # Call the LLM to evaluate whether the current query is a follow-up question
        followup_response = self.model_engine.call_helper(query=query, prompt=prompt)

        # The prompt asks for 'yes'/'no', but models routinely answer with a
        # boolean word instead ("True"/"False"), so accept either spelling.
        return followup_response.strip().lower() in {"yes", "true", "y"}

    def _handle_exploration_query(self, user_query):
        """
        Handle queries about available data and variables

        Returns:
            Detailed information about database schema and available data
        """
        relevant_knowledge = self._retrieve_relevant_knowledge(user_query)

        # Prepare prompt for data exploration
        exploration_prompt = f"""Database Schema Overview
        Database Schema: {self.schema_info}
        Relevant Knowledge: {relevant_knowledge}

        Answer user's question by analyzing relevant Database schema and relevant knowledge.
        Provide a clear, user-friendly explanation.

        Response Requirements:
        - Answer in the same language as the user’s query.
        - Use a clear and structured format (e.g., bullet points, tables).
        - Do not provide SQL queries.
        - Keep the response within 500 words.
        """

        # Generate exploration response
        exploration_response = self.model_engine.call_helper(
            query=user_query, prompt=exploration_prompt
        )

        return exploration_response

    def _needs_explore(self, query):
        prompt = f"""
        Task: Determine if the user is asking a **general exploratory question** about available **data, indicators, metrics, categories, or entities** in a database.
        ### **Exploratory Question Examples** (Answer 'yes' if similar):
        - "What metrics can I query?"
        - "What data is available?"
        - "What kinds of failures are recorded?"
        - "What types of vehicles exist?"
        - "What can I analyze in this dataset?"
        - "Tell me about the available fields in the database."
        
        ### **Non-Exploratory Questions** (Answer 'no' if similar):
        - "What is the failure rate of vehicle type A?"
        - "How many failures happened last month?"
        - "Show me the top 10 most frequent failure types."
        - "What is the average speed of all vehicles?"
        - "Retrieve data for vehicle ID 1234."
        
        **Response Format:**  
        - Reply with only `'yes'` if the query is exploratory.  
        - Reply with only `'no'` if the query is specific.  
        - No extra text, explanations, or formatting.

        User Query: {query}
        """
        response = self.model_engine.call_helper(query=query, prompt=prompt)
        return response

    def _should_compact(self, session: ChatSession) -> bool:
        if len(session.history) > MAX_HISTORY_TURNS:
            return True
        chars = sum(len(turn.user) + len(turn.system) for turn in session.history)
        return chars > MAX_HISTORY_CHARS

    def _compact_session(self, session: ChatSession) -> bool:
        """Replace older turns with an LLM summary; best-effort, never blocks."""
        # Normally keep the most recent 8 turns, but a short history can still
        # exceed the char budget, so keep at least one turn and summarize the rest.
        keep = min(KEEP_RECENT_TURNS, max(1, len(session.history) - 1))
        older = session.history[:-keep]
        if not older:
            return False
        turns_text = "".join(
            f"User: {turn.user}\nAssistant: {turn.system}\n\n" for turn in older
        )
        prompt = f"""你是一个 NL2SQL 对话压缩器。把下面的对话压缩成 200-300 字摘要，供后续生成 SQL 使用。
必须保留：用户意图、filter（日期范围、类别等）、表/列名、最后一版 SQL、用户的纠正、未解决的问题。
省略：寒暄、重复解释、已经解决的无关问题。
如果已有摘要，请把它和新增对话合并，不要重复计算。
已有摘要：{session.summary or "无"}
需要压缩的对话：
{turns_text}
只输出摘要，不要加标题。"""
        try:
            summary = self.model_engine.call_helper(
                query="请压缩以上对话。", prompt=prompt
            )
        except Exception as exc:  # noqa: BLE001 - compaction is best-effort
            logger.warning("Session compaction failed: %s", exc)
            return False
        if not summary or not summary.strip():
            logger.warning("Session compaction returned an empty summary")
            return False
        session.summary = summary.strip()[:MAX_SUMMARY_CHARS]
        session.summary_upto += len(older)
        session.history = session.history[-keep:]
        return True

    def _finalize_analysis(self, results, user_query, session: ChatSession):
        # Call helper_llm for natural language analysis of results
        results_text = str(results[:MAX_ANALYSIS_ROWS])
        if len(results) > MAX_ANALYSIS_ROWS:
            results_text += f"\n(showing {MAX_ANALYSIS_ROWS} of {len(results)} rows)"
        if len(results_text) > MAX_ANALYSIS_CHARS:
            results_text = results_text[:MAX_ANALYSIS_CHARS] + "\n...(truncated)"

        analysis_prompt = f"""
        Given the user's conversation summary: {session.summary}
        Recent conversation: {session.history[-KEEP_RECENT_TURNS:]}
        The SQL query results: {results_text}
        The most recent user query: {user_query}

        Please provide a natural language analysis of the SQL results and a general summary that incorporates all relevant user inputs.
        """
        analysis_response = self.model_engine.call_llm(query=user_query, prompt=analysis_prompt)

        return analysis_response

    def _classify_non_sql(
        self, generated_text
    ) -> tuple[Literal["refuse", "clarification"] | None, str]:
        """Classify a model reply that is not SQL.

        Returns ``("refuse" | "clarification" | None, message)``. Delegates to
        the shared parser so eval and production cannot disagree about whether a
        reply is a refusal or a clarification.
        """
        result = parse_generation(generated_text)
        if result.kind == "refuse":
            return "refuse", result.message or "当前数据无法支持该问题。"
        if result.kind == "clarify":
            return "clarification", result.message
        return None, ""

    def _extract_sql_query(self, generated_text):
        """Extract the SQL statement using the shared generation parser.

        The prompt asks for ``SQL_QUERY:``, but models occasionally return a
        fenced or plain statement instead. Treat those as SQL rather than as an
        abstention: parsing is a formatting concern, not a capability.
        """
        return parse_generation(generated_text).sql or None

    def _validate_sql(self, query):
        """Parse the statement and enforce a single read-only SELECT.

        This is a pre-flight check, not the security boundary: the database
        read-only role is what actually prevents writes.
        """
        try:
            statements = [
                statement
                for statement in sqlglot.parse(query, read="postgres")
                if statement is not None
            ]
        except SqlglotError as exc:
            return False, f"SQL parse error: {exc}"

        if len(statements) != 1:
            return False, "Only a single SQL statement is allowed"

        statement = statements[0]
        if not isinstance(statement, (exp.Select, exp.Union, exp.Intersect, exp.Except)):
            return False, (
                f"Only SELECT queries are allowed, got {type(statement).__name__}"
            )

        # SELECT ... INTO creates a table, so it is a write despite the SELECT.
        if statement.args.get("into") is not None or statement.find(exp.Into) is not None:
            return False, "SELECT INTO is not allowed"

        cte_names = {
            cte.alias_or_name.lower() for cte in statement.find_all(exp.CTE)
        }
        tables = {
            table.name.lower()
            for table in statement.find_all(exp.Table)
            if table.name and table.name.lower() not in cte_names
        }
        unknown = tables - {name.lower() for name in self.schema_info}
        if unknown:
            return False, f"Query references unknown table: {sorted(unknown)[0]}"

        return True, "Valid query"

    def process_query(self, user_query, session_id: str | None = None):
        """Process a natural language query and return the legacy text response."""
        return self.process_query_structured(user_query, session_id).render_text()

    def process_query_structured(
        self, user_query, session_id: str | None = None
    ) -> ChatResult:
        """Process a query and return a typed result for the presentation layer."""
        start_time = time.time()
        try:
            session_id = normalize_session_id(session_id)
        except ValueError as exc:
            return ChatResult(kind="invalid", message=str(exc))

        try:
            session = self.sessions.get(session_id)
        except SessionStoreUnavailable as exc:
            return ChatResult(kind="store_error", message=str(exc))

        # Compact before building this turn's prompt so the prompt is bounded.
        if self._should_compact(session):
            self._compact_session(session)

        usage = TokenUsage()
        usage_token = set_request_usage(usage)

        def finish(result: ChatResult) -> ChatResult:
            result.processing_time_ms = (time.time() - start_time) * 1000
            result.prompt_tokens = usage.prompt_tokens
            result.completion_tokens = usage.completion_tokens
            result.cached_tokens = usage.cached_tokens
            result.calls = usage.calls
            if result.kind in ("sql", "execution_error", "too_many_rows"):
                session.last_sql = result.sql
            session.history[-1].system = result.history_text()
            try:
                self.sessions.save(session_id, session)
            except SessionStoreUnavailable as exc:
                return ChatResult(kind="store_error", message=str(exc))
            return result

        try:
            # Add to conversation history
            if session.history and not session.history[-1].system:
                # Update last turn if system hasn't responded yet
                session.history[-1].user = user_query
            else:
                session.history.append(Turn(user=user_query))

            _is_exploration = self._needs_explore(user_query)
            if "yes" in _is_exploration:
                exploration_response = self._handle_exploration_query(user_query)
                return finish(
                    ChatResult(kind="exploration", message=exploration_response)
                )

            # Prepare prompt and generate response
            prompt = self._prepare_prompt(user_query, session)
            # generated_text = self.nlp_pipeline(prompt)[0]['generated_text'] # if call local llm
            generated_text = self.model_engine.call_coder(
                query=user_query, prompt=prompt
            )

            # Refusal and clarification are distinct user-facing outcomes.
            non_sql_kind, non_sql_message = self._classify_non_sql(generated_text)
            if non_sql_kind:
                return finish(ChatResult(kind=non_sql_kind, message=non_sql_message))

            # Extract and validate SQL_QUERY
            sql_query = self._extract_sql_query(generated_text)
            if not sql_query:
                return finish(
                    ChatResult(
                        kind="invalid",
                        message="I couldn't generate a valid SQL_QUERY. Can you rephrase your question?",
                    )
                )

            is_valid, validation_message = self._validate_sql(sql_query)
            if not is_valid:
                return finish(
                    ChatResult(
                        kind="invalid",
                        message=f"Generated SQL_QUERY is not valid: {validation_message}",
                    )
                )

            # Execute query and return results
            result = self.db.execute_query(sql_query)

            # A failed execution is not a result: return it directly, without
            # sending the error to the analysis model.
            if not result.executed:
                return finish(
                    ChatResult(
                        kind="execution_error",
                        sql=sql_query,
                        message=result.error or "",
                        execution_time_ms=result.execution_time_ms,
                    )
                )

            rows = result.result or []

            # Guard the analysis prompt: a huge result means the query did not
            # converge. Warn and skip analysis rather than feeding it 50k rows.
            if len(rows) > MAX_ANALYSIS_ROWS:
                return finish(
                    ChatResult(
                        kind="too_many_rows",
                        sql=sql_query,
                        rows=rows[:MAX_ANALYSIS_ROWS],
                        total_rows=len(rows),
                        truncated=True,
                        message=(
                            f"存在 {len(rows)} 条返回记录，超出可分析范围"
                            f"（上限 {MAX_ANALYSIS_ROWS}）。"
                            "请缩小时间范围或增加过滤条件后重试。"
                        ),
                        execution_time_ms=result.execution_time_ms,
                    )
                )

            # Combine the SQL response with the analysis
            analysis_response = self._finalize_analysis(rows, user_query, session)
            return finish(
                ChatResult(
                    kind="sql",
                    sql=sql_query,
                    rows=rows,
                    total_rows=len(rows),
                    analysis=analysis_response,
                    execution_time_ms=result.execution_time_ms,
                )
            )
        finally:
            reset_request_usage(usage_token)

    def add_document(self, file_path: str) -> str:
        """
        Add a new document to the knowledge base

        Args:
            file_path: Path to the document file

        Returns:
            Result message
        """
        result = self.knowledge_base.add_document(file_path, self.doc_processor)

        self.knowledge_base.save()  # Update cache
        return result
    
    def generate_sql(self, user_query: str) -> str:
        """
        Generate SQL query from natural language input without executing it.

        Args:
            user_query: Natural language query
        """
        prompt = self._prepare_prompt(user_query, ChatSession())
        generated_text = self.model_engine.call_coder(query=user_query, prompt=prompt)

        non_sql_kind, non_sql_message = self._classify_non_sql(generated_text)
        if non_sql_kind:
            return non_sql_message

        # Extract and validate SQL_QUERY
        sql_query = self._extract_sql_query(generated_text)
        if not sql_query:
            return "I couldn't generate a valid SQL_QUERY. Can you rephrase your question?"

        is_valid, validation_message = self._validate_sql(sql_query)
        if not is_valid:
            return f"Generated SQL_QUERY is not valid: {validation_message}"

        return sql_query
