# data_explorer_agent.py
import asyncio
import pandas as pd
import openai
from azure.kusto.data import KustoClient, KustoConnectionStringBuilder
from decouple import config
from semantic_kernel import Kernel
from semantic_kernel.contents.chat_history import ChatHistory
from decouple import config


# Retrieve credentials from your environment variables
ADX_CLUSTER   =  'https://devadx.eastus2.kusto.windows.net'   # E.g., "https://<your-cluster>.kusto.windows.net"
ADX_DATABASE  = 'cti'
AOAI_API_KEY  =  config('api_key')
AOAI_BASE_URL = 'https://jb-ai-test.openai.azure.com/'     # E.g., "https://<your-resource-name>.openai.azure.com/"
AOAI_MODEL    = config('aoai_model', default="gpt-4o")  # Your deployment model name

# Configure OpenAI SDK for Azure OpenAI
openai.api_key = AOAI_API_KEY
openai.api_base = AOAI_BASE_URL
class DataExplorerAgent:
    def __init__(self, agent_name: str, kernel: Kernel):
        self.agent_name = agent_name
        self.kernel = kernel
        self.chat_history = ChatHistory()
        self._configure_adx()

    def _configure_adx(self):
        # Here we create a connection string with your preferred authentication method.
        # In this example, we use device authentication.
        print('creating connection string')
        kcsb = KustoConnectionStringBuilder.with_aad_device_authentication(ADX_CLUSTER)
        print('initializing Kusto client')
        self.kusto_client = KustoClient(kcsb)
        print('client initialized')

    async def retrieve_and_summarize(self, adx_query: str) -> str:
        """
        Query Azure Data Explorer using the provided query, then pass the JSON data
        to AOAI to summarize and highlight discrepancies.
        """
        loop = asyncio.get_event_loop()

        # Run the ADX query in a separate thread since the Kusto client is synchronous
        print('executing ADX query')
        response = await loop.run_in_executor(None, self.kusto_client.execute, ADX_DATABASE, adx_query)

        # Convert the results to JSON using pandas
        df = pd.DataFrame(response.primary_results[0])
        json_data = df.to_json(orient="records")

        # Prepare the prompt for summarization
        prompt = (
            "Summarize the following JSON data retrieved from an ADX query. "
            "If there are multiple records, highlight any discrepancies or trends over time:\n\n"
            f"{json_data}"
        )

        # Call AOAI synchronously within a run_in_executor
        ai_response = await loop.run_in_executor(
            None,
            lambda: openai.ChatCompletion.create(
                model=AOAI_MODEL,
                messages=[
                    {"role": "system", "content": "You are an assistant that summarizes data and detects discrepancies."},
                    {"role": "user", "content": prompt}
                ]
            )
        )

        result = ai_response["choices"][0]["message"]["content"]
        return result

    async def run_task(self, query: str) -> str:
        # Alias run_task to retrieve_and_summarize to meet the generic interface used in your routes.
        print ('running task')
        return await self.retrieve_and_summarize(query)