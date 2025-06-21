import OpenAI from 'openai';
import { SearchClient, AzureKeyCredential } from '@azure/search-documents';
import { Message, Suggestion } from '../types/conversation';

// Load configuration from environment variables (set in .env)
const openaiEndpoint = process.env.REACT_APP_OPENAI_ENDPOINT!;
const openaiApiKey = process.env.REACT_APP_OPENAI_API_KEY!;
const openaiDeployment = process.env.REACT_APP_OPENAI_DEPLOYMENT!;
const searchEndpoint = process.env.REACT_APP_AZURE_SEARCH_ENDPOINT!;
const searchApiKey = process.env.REACT_APP_AZURE_SEARCH_API_KEY!;
const searchIndexName = process.env.REACT_APP_SEARCH_INDEX_NAME!;

// Initialize Azure AI Search client
const searchClient = new SearchClient(
  searchEndpoint,
  searchIndexName,
  new AzureKeyCredential(searchApiKey)
);

// Initialize OpenAI client for Azure (browser-compatible)
const openaiClient = new OpenAI({
  apiKey: openaiApiKey,
  dangerouslyAllowBrowser: true,
  baseURL: `${openaiEndpoint}/openai/deployments/${openaiDeployment}`,
  defaultQuery: { 'api-version': '2024-02-15-preview' },
  defaultHeaders: {
    'api-key': openaiApiKey,
  },
});

// Use same Azure OpenAI chat endpoint for alt RAG call
const altEndpoint = `${openaiEndpoint}/openai/deployments/${openaiDeployment}/chat/completions?api-version=2024-02-15-preview`;

/**
 * Send a combined RAG payload to the alt endpoint and return the assistant's reply.
 */
export async function getSellerResponse(
  seller: string,
  buyer: string,
  product: string,
  buyerMessage: string,
  conversationHistory: Message[] = []
): Promise<string> {
  // Build sample payload merging search configuration and chat messages
  const payload = {
    data_sources: [
      {
        type: 'azure_search',
        parameters: {
          endpoint: searchEndpoint,
          index_name: searchIndexName,
          semantic_configuration: `${searchIndexName}-semantic-configuration`,
          query_type: 'vector_semantic_hybrid',
          fields_mapping: {
            content_fields_separator: '\n',
            content_fields: ['chunk'],
            filepath_field: 'chunk_id',
            title_field: 'title',
            url_field: null,
            vector_fields: ['text_vector']
          },
          in_scope: true,
          role_information: `You are ${seller}, a seller of premium ${product}.`,
          filter: null,
          strictness: 3,
          top_n_documents: 5,
          authentication: { type: 'api_key', key: searchApiKey },
          embedding_dependency: { type: 'gpt-4o', deployment_name: 'text-embedding-3-large' },
          key: searchApiKey,
          indexName: searchIndexName
        }
      }
    ],
    messages: [
      { role: 'system', content: `You are ${seller}, a seller of premium ${product}. Respond conversationally to ${buyer}.` },
      ...conversationHistory.slice(-10).map(m => ({ role: m.role === 'Buyer' ? 'user' : 'assistant', content: m.message })),
      { role: 'user', content: buyerMessage }
    ],
    temperature: 0.7,
    top_p: 0.95,
    max_tokens: 800,
    stop: null,
    stream: false,
    past_messages: 10,
    frequency_penalty: 0,
    presence_penalty: 0,
    azureSearchEndpoint: searchEndpoint,
    azureSearchKey: searchApiKey,
    azureSearchIndexName: searchIndexName
  };

  const res = await fetch(altEndpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  if (!res.ok) throw new Error(`Alt RAG request failed: ${res.status}`);
  const data = await res.json();
  // Expecting { choices: [ { message: { content } } ] }
  return data.choices?.[0]?.message?.content?.trim() || '';
}

/**
 * Alternative fallback function that generates responses without RAG if search fails
 */
export async function getSellerResponseSimple(
  seller: string,
  buyerMessage: string
): Promise<string> {
  // Could bypass search and call altEndpoint similarly or fallback
  return getSellerResponse(seller, '', '', buyerMessage, []);
}

// Placeholder implementations to match primary interface
export async function retrieveContext(query: string, topK: number = 5): Promise<string[]> {
  console.warn('aiServiceRAG-alt: retrieveContext placeholder called');
  return [];
}

export async function getBuyerInitialMessage(buyer: string, product: string): Promise<string> {
  console.warn('aiServiceRAG-alt: getBuyerInitialMessage placeholder called');
  return `Hi, I'm interested in ${product}.`;
}

export async function getPatternAnalysisSuggestions(conversation: Message[]): Promise<Suggestion[]> {
  console.warn('aiServiceRAG-alt: getPatternAnalysisSuggestions placeholder called');
  return [];
}

export async function getSuggestionDetails(query: string, topK: number = 5): Promise<string[]> {
  console.warn('aiServiceRAG-alt: getSuggestionDetails placeholder called');
  return [];
}

// Placeholder for translation function to match primary interface
export async function translateText(text: string, targetLang: string): Promise<string> {
  console.warn('aiServiceRAG-alt: translateText placeholder called');
  return text;
}
