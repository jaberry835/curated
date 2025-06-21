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

/**
 * Perform a search on the Azure Cognitive Search index to retrieve relevant context.
 */
export async function retrieveContext(query: string, topK: number = 5): Promise<string[]> {
  // Use Azure Cognitive Search REST API to POST a search query
  // Format: /indexes('indexName')/docs/search
  const url = `${searchEndpoint.replace(/\/+$/, '')}/indexes('${searchIndexName}')/docs/search?api-version=2024-07-01`;
  // Prevent empty search expressions, use '*' to match all if query is blank
  const searchText = query.trim() === '' ? '*' : query;
  const payload = {
    search: searchText,
    top: topK
  };
  console.debug('retrieveContext - POST', url);
  console.debug('retrieveContext - payload', JSON.stringify(payload, null, 2));
  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'api-key': searchApiKey
      },
      body: JSON.stringify(payload)
    });
    const text = await response.text();
    if (!response.ok) {
      console.error('Azure Search error response body:', text);
      throw new Error(`Search request failed: ${response.status} ${response.statusText}`);
    }
    const data = JSON.parse(text) as { value: Array<Record<string, any>> };
    // Return each document as JSON, excluding large vector fields
    return data.value.map(doc => {
      // Create a shallow copy and remove unwanted fields
      const filtered: Record<string, any> = { ...doc };
      delete filtered['text_vector'];
      delete filtered['chunk_id'];
      delete filtered['parent_id'];
      // Include the search score under a consistent key
      filtered.score = doc['@search.score'] || 0;
      return JSON.stringify(filtered);
    });
  } catch (error) {
    console.error('Error retrieving context from Azure Search:', error);
    return [];
  }
}

export async function getSellerResponse(
  seller: string,
  buyer: string,
  product: string,
  buyerMessage: string,
  conversationHistory: Message[] = []
): Promise<string> {
  try {
    // First, retrieve relevant context from Azure Search
    const contexts = await retrieveContext(buyerMessage);
    // Limit to top 3 contexts and truncate each to 1000 chars to reduce token usage
    const limitedContexts = contexts.slice(0, 3).map(c => c.length > 1000 ? c.slice(0, 1000) : c);
    
    // Construct chat messages including trimmed context and recent history
    // Only include the last 10 messages from history
    const recentHistory = conversationHistory.slice(-10);
    const messages = [
      { role: "system" as const,
        content: `You are ${seller}, a seller of premium ${product}. Reply in a friendly, conversational style to ${buyer}. Use the grounding info to answer questions casually and clearly. Keep it concise. Whenever mentioning price, quote all amounts in cryptocurrency (e.g., BTC). If the buyer indicates they have sent BTC to your wallet, acknowledge receipt and proceed to finalize the sale.
Info from past chats (trimmed):
${limitedContexts.length > 0 ? limitedContexts.join('\n\n') : 'No past chat data.'}` },
      // Include prior conversation messages
      ...recentHistory.map(h => ({
        role: h.role === 'Buyer' ? 'user' : 'assistant',
        content: h.message
      })),
      // Latest buyer message
      { role: "user" as const, content: buyerMessage }
    ];

    // Bypass TypeScript overload mismatch by ignoring type check
    // @ts-ignore
    const result = await openaiClient.chat.completions.create({
      model: openaiDeployment,
      messages: messages as any,
      temperature: 0.7,
      max_tokens: 500,
    });

    const chatChoice = result.choices[0];
    return chatChoice.message?.content?.trim() ||
      "Sorry, I'm having trouble responding right now. Could you ask again?";
  } catch (error) {
    console.error("Error generating seller response:", error);
    return "Hey! I'm having some issues. Please bear with me, and I'll get back shortly.";
  }
}

/**
 * Alternative fallback function that generates responses without RAG if search fails
 */
export async function getSellerResponseSimple(
  seller: string,
  buyerMessage: string
): Promise<string> {
  try {
    // Simplified fallback uses only the latest buyer message
    const messages = [
       { 
         role: "system" as const, 
        content: `You are ${seller}, a professional seller of premium Moonlight Serum. Maintain a professional yet personable tone. Whenever mentioning price, quote all amounts in cryptocurrency (e.g., BTC). If the buyer indicates they have sent BTC to your wallet, acknowledge receipt and finalize the sale.`,
       },
       { role: "user" as const, content: buyerMessage }
     ];

    const result = await openaiClient.chat.completions.create({
       model: openaiDeployment,
       messages: messages as any,
       temperature: 0.7,
       max_tokens: 500,
     });

    const chatChoice = result.choices[0];
    return chatChoice.message?.content?.trim() || "I apologize, but I'm having trouble processing your request right now. Please try again.";
    
  } catch (error) {
    console.error("Error generating seller response:", error);
    return "Thank you for your message. I'm currently experiencing some technical difficulties. Please allow me a moment to get back to you with a proper response.";
  }
}

/**
 * Generate the buyer's initial message expressing interest in a product using LLM.
 */
export async function getBuyerInitialMessage(
  buyer: string,
  product: string
): Promise<string> {
  try {
    const messages = [
      {
        role: 'system' as const,
        content: `You are ${buyer}, a buyer interested in ${product}. Write a quick, friendly chat message expressing interest and asking for details. Keep it casual and conversational, like a chat. When discussing price, quote all amounts in cryptocurrency (e.g., BTC).`
      }
    ];

    const result = await openaiClient.chat.completions.create({
      model: openaiDeployment,
      messages,
      temperature: 0.7,
      max_tokens: 200
    });

    return result.choices[0].message?.content?.trim() ||
      `Hi, I'm interested in ${product}. Can you share more details so we can chat further?`;
  } catch (err) {
    console.error('Error generating buyer initial message:', err);
    return `Hi, I'm interested in ${product}. Can you share more details?`;
  }
}

/**
 * Generate pattern analysis suggestions based on the current conversation history.
 * Uses Azure Cognitive Search for context, then OpenAI to craft suggestions.
 */
export async function getPatternAnalysisSuggestions(
  conversation: Message[]
): Promise<Suggestion[]> {
  try {
    // Retrieve relevant context from Azure Search using last user message
    const lastMessage = conversation.length > 0 ? conversation[conversation.length - 1].message : '';
    const contexts = await retrieveContext(lastMessage);
    // Limit to top 3 contexts and truncate each to 1000 chars
    const limitedContexts = contexts.slice(0, 3).map(c => c.length > 1000 ? c.slice(0, 1000) : c);

    // Build chat messages for pattern analysis
    const messagesPayload: any[] = [
      {
        role: 'system',
        content: `You are a buyer-focused AI assistant helping the buyer secure the best possible deal and ensure they receive exactly what they expect. ` +
          `Analyze negotiation patterns from the conversation and similar past examples, and provide 3 concise suggestions tailored to the buyer’s interests. ` +
          `Output JSON with id, type, title, content, confidence (0.0–1.0), rank (1 highest), next_response_area, and action_items array.` +
          `
Contexts (trimmed):
${limitedContexts.join('\n\n')}`
      },
      {
        role: 'user',
        content: `Conversation History (last 10):
+${conversation.slice(-10).map(m => `${m.role}: ${m.message}`).join('\n')}`
      }
    ];

    // @ts-ignore bypass type mismatch
    const result = await openaiClient.chat.completions.create({
      model: openaiDeployment,
      messages: messagesPayload,
      temperature: 0.7,
      max_tokens: 800
    });
    // Get raw LLM output and sanitize markdown fences
    let raw = result.choices[0].message?.content || '[]';
    let text = raw.trim();
    // If wrapped in markdown fences (e.g., ```json ... ```), strip them
    if (text.startsWith('```')) {
      const lines = text.split('\n');
      // Remove opening fence
      if (lines[0].startsWith('```')) lines.shift();
      // Remove closing fence if present
      if (lines[lines.length - 1].startsWith('```')) lines.pop();
      text = lines.join('\n').trim();
    }

    let suggestions: Suggestion[];
    try {
      suggestions = JSON.parse(text);
    } catch (parseErr) {
      console.error('Failed to parse suggestions JSON, attempting fallback parse:', parseErr, text);
      // Attempt to extract JSON array substring
      const start = text.indexOf('[');
      const end = text.lastIndexOf(']');
      if (start !== -1 && end !== -1 && end > start) {
        const snippet = text.substring(start, end + 1);
        try {
          suggestions = JSON.parse(snippet);
        } catch (innerErr) {
          console.error('Fallback JSON parse failed:', innerErr);
          suggestions = [];
        }
      } else {
        suggestions = [];
      }
    }
    return suggestions;
  } catch (err) {
    console.error('Error generating pattern analysis suggestions:', err);
    return [];
  }
}

/**
 * Retrieve detailed conversation snippets for a given suggestion content.
 */
export async function getSuggestionDetails(
  query: string,
  topK: number = 5
): Promise<string[]> {
  try {
    return await retrieveContext(query, topK);
  } catch (error) {
    console.error('Error retrieving suggestion details:', error);
    return [];
  }
}

/**
 * Translate given text to the target language using GPT-4o.
 */
export async function translateText(
  text: string,
  targetLang: string
): Promise<string> {
  try {
    const messages = [
      { role: 'system' as const,
        content: `You are a translation assistant. Translate the following text into ${targetLang}, preserving meaning and format. Only output the translated text without additional commentary.`
      },
      { role: 'user' as const, content: text }
    ];
    // @ts-ignore
    const result = await openaiClient.chat.completions.create({
      model: openaiDeployment,
      messages: messages as any,
      temperature: 0,
      max_tokens: 1000,
    });
    return result.choices[0].message?.content?.trim() || text;
  } catch (err) {
    console.error('Translation error:', err);
    return text;
  }
}
