import asyncio
import pandas as pd
import openai
from azure.kusto.data import KustoClient, KustoConnectionStringBuilder
from decouple import config
from semantic_kernel import Kernel
from semantic_kernel.contents.chat_history import ChatHistory

# Retrieve credentials from environment variables
ADX_CLUSTER = 'https://devadx.eastus2.kusto.windows.net'  
ADX_DATABASE = 'cti'
AOAI_API_KEY = config('api_key')
AOAI_BASE_URL = 'https://jb-ai-test.openai.azure.com/'     
AOAI_MODEL = config('aoai_model', default="gpt-4o")
CLIENT_ID = config('client_id')
CLIENT_SECRET = config('client_secret')
TENANT_ID = config('client_tenant_id')
# Configure OpenAI SDK
client = openai.OpenAI(api_key=AOAI_API_KEY, base_url=AOAI_BASE_URL)

class DataExplorerAgent:
    def __init__(self, agent_name: str, kernel: Kernel):
        self.agent_name = agent_name
        self.kernel = kernel
        self.chat_history = ChatHistory()
        self._configure_adx()

    def _configure_adx(self):
        print('Creating connection string...')
       
        kcsb = KustoConnectionStringBuilder.with_aad_application_key_authentication(ADX_CLUSTER, CLIENT_ID, CLIENT_SECRET, TENANT_ID)
        self.kusto_client = KustoClient(kcsb)
        print('Kusto client initialized.')

    async def retrieve_and_summarize(self, adx_query: str) -> str:
        """
        Query Azure Data Explorer using the provided query, then summarize results with AOAI.
        """
        print('Running ADX query...')
        loop = asyncio.get_event_loop()
        print('Running ADX query...')
        # Run ADX query
        response = await loop.run_in_executor(None, self.kusto_client.execute, ADX_DATABASE, adx_query)

        print('Response Recieved...')
        # Convert results to JSON
        print('extracting data...')
        df = pd.DataFrame(response.primary_results[0])
        print('extracting records')
        json_data = df.to_json(orient="records")

        client = openai.OpenAI(api_key=AOAI_API_KEY, base_url="https://jb-ai-test.openai.azure.com/")

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are an AI assistant."},
                {"role": "user", "content": "Hello!"}
            ],
            timeout=10
        )

        print(response.choices[0].message.content)


        # Prepare prompt
        prompt = (
            "Summarize the following JSON data retrieved from an ADX query. "
            "Highlight discrepancies or trends:\n\n"
            f"{json_data}"
        )
        print('passing to AOAI...')
        #print('Prompt:', prompt)
        # Call AOAI using latest SDK
        print(f"Using OpenAI API Key: {AOAI_API_KEY[:5]}****")  # Safe obfuscation
        print(f"Using AOAI Model: {AOAI_MODEL}")
        ai_response = await loop.run_in_executor(
            None,
            lambda: client.chat.completions.create(
                model=AOAI_MODEL,
                messages=[
                    {"role": "system", "content": "You are an assistant that summarizes data and detects discrepancies."},
                    {"role": "user", "content": 'test echo this'}
                ]
            )
        )
        print('Response Recieved...')
        result = ai_response.choices[0].message.content
        print('result:', result)
        return result

    async def run_task(self, query: str) -> str:
        print('Running task...')
        return await self.retrieve_and_summarize(query)
