from openai import OpenAI

from app.config import settings


class SiliconFlowLLM:
    def __init__(self):
        self.SILICON_FLOW_API_KEY = settings.silicon_flow_api_key.get_secret_value()
        self.SILICON_FLOW_BASE_URL = str(settings.silicon_flow_base_url)

        # models
        self.SILICON_FLOW_REASONING_MODEL = settings.reasoning_model
        self.SILICON_FLOW_NL2SQL_MODEL = settings.nl2sql_model
        self.SILICON_FLOW_HELPER_MODEL = settings.helper_model
        print("-" * 50)
        print(
            f"""\ncoder llm: {self.SILICON_FLOW_NL2SQL_MODEL}\nreasoning llm: {self.SILICON_FLOW_REASONING_MODEL}\nhelper llm: {self.SILICON_FLOW_HELPER_MODEL}\n"""
        )
        print("-" * 50)

        # client
        self.client = OpenAI(api_key=self.SILICON_FLOW_API_KEY, base_url=self.SILICON_FLOW_BASE_URL)

    def call_coder(self, query, prompt):
        response = self.client.chat.completions.create(
            model=self.SILICON_FLOW_NL2SQL_MODEL,
            messages=[{"role": "system", "content": prompt}, {"role": "user", "content": query}],
            temperature=0.7,
            max_tokens=4096,
        )
        content = response.choices[0].message.content
        return content

    def call_llm(self, query, prompt):
        response = self.client.chat.completions.create(
            model=self.SILICON_FLOW_REASONING_MODEL,
            messages=[{"role": "system", "content": prompt}, {"role": "user", "content": query}],
            temperature=0.7,
            max_tokens=4096,
        )
        content = response.choices[0].message.content
        return content

    def call_helper(self, query, prompt):
        response = self.client.chat.completions.create(
            model=self.SILICON_FLOW_HELPER_MODEL,
            messages=[{"role": "system", "content": prompt}, {"role": "user", "content": query}],
            temperature=0.7,
            max_tokens=4096,
        )
        content = response.choices[0].message.content
        return content
