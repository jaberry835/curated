import { SearchClient, AzureKeyCredential } from '@azure/search-documents';
import OpenAI from 'openai';


// Load configuration from environment variables (set in .env)
const searchEndpoint = process.env.REACT_APP_AZURE_SEARCH_ENDPOINT!;
const searchApiKey = process.env.REACT_APP_AZURE_SEARCH_API_KEY!;
const searchIndexName = process.env.REACT_APP_SEARCH_INDEX_NAME!;
const openaiEndpoint = process.env.REACT_APP_OPENAI_ENDPOINT!;
const openaiApiKey = process.env.REACT_APP_OPENAI_API_KEY!;
const openaiDeployment = process.env.REACT_APP_OPENAI_DEPLOYMENT!;

// Initialize Azure AI Search client
const searchClient = new SearchClient(
  searchEndpoint,
  searchIndexName,
  new AzureKeyCredential(searchApiKey)
);

// Initialize OpenAI client for Azure
const openaiClient = new OpenAI({
  apiKey: openaiApiKey,
  dangerouslyAllowBrowser: true,
  baseURL: `${openaiEndpoint}/openai/deployments/${openaiDeployment}`,
  defaultQuery: { 'api-version': '2024-02-15-preview' },
  defaultHeaders: {
    'api-key': openaiApiKey,
  },
});

/**
 * Perform a semantic search on the Azure Cognitive Search index to retrieve relevant context.
 */
async function retrieveContext(query: string, topK: number = 10): Promise<string[]> {
  const results = await searchClient.search<string>(query, {
    top: topK,
    // Remove semanticConfigurationName as it's not supported in basic search
  });

  const contexts: string[] = [];
  for await (const result of results.results) {
    if (result.document) {
      contexts.push(JSON.stringify(result.document));
    }
  }
  return contexts;
}

/**
 * Generate a seller response using Azure OpenAI chat completions with RAG context.
 */
export async function getSellerResponse(buyerMessage: string): Promise<string> {
  // Retrieve grounding documents
  const contexts = await retrieveContext(buyerMessage);

  // Build chat messages for system and user
  const systemPrompt = {
    role: 'system' as const,
    content: `You are SilverHawk, a seller of premium Moonlight Serum. Use the following grounding data from past conversations and product specifications to craft a helpful, secure, and persuasive response to the buyer. Incorporate relevant details and maintain a professional tone.`
  };

  const userPrompt = {
    role: 'user' as const,
    content: `Buyer says: "${buyerMessage}"\n\nGrounding Data:\n${contexts.join('\n')}`
  };
  // Call Azure OpenAI chat endpoint
  const result = await openaiClient.chat.completions.create({
    model: openaiDeployment, // Add the required model parameter
    messages: [systemPrompt, userPrompt],
    temperature: 0.7,
    max_tokens: 500,
  });

  // Extract the seller's reply
  const chatChoice = result.choices[0];
  return chatChoice.message?.content?.trim() || '';
}
