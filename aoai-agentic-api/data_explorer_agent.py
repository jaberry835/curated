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
        # In this example, we use device authentication. You might prefer another method.
        kcsb = KustoConnectionStringBuilder.with_aad_device_authentication(ADX_CLUSTER)
        self.kusto_client = KustoClient(kcsb)

    async def retrieve_and_summarize(self, adx_query: str) -> str:
        """
        Query Azure Data Explorer using the provided query, then pass the JSON data
        to AOAI (via Azure OpenAI) to summarize and optionally point out discrepancies.
        """
        loop = asyncio.get_event_loop()

        # Run the ADX query in a separate thread (since Azure Kusto library is synchronous)
        response = await loop.run_in_executor(None, self.kusto_client.execute, ADX_DATABASE, adx_query)

        # Convert the query results to a JSON string
        df = pd.DataFrame(response.primary_results[0])
        json_data = df.to_json(orient="records")

        # Build the prompt dynamically depending on the number of records
        prompt = ("Summarize the following JSON data returned from an Azure Data Explorer query. "
                  "If there are multiple records, highlight any discrepancies or trends over time.\n\n" 
                  f"{json_data}")

        # Use run_in_executor if you prefer non-blocking behavior (since openai.ChatCompletion.create is synchronous)
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
