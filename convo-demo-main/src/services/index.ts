import * as RAG from './aiServiceRAG';
import * as RAGAlt from './aiServiceRAG-alt';

// Toggle using environment variable (ensure to restart after changing .env)
const useAlt = process.env.REACT_APP_USE_ALT_RAG?.toLowerCase() === 'true';
console.log('aiServiceRAG: useAlt flag is', useAlt, ' (REACT_APP_USE_ALT_RAG=', process.env.REACT_APP_USE_ALT_RAG, ')');

// Export all services, choosing alt implementation for RAG functions when flagged
export const retrieveContext = useAlt
  ? RAGAlt.retrieveContext
  : RAG.retrieveContext;

export const getSellerResponse = useAlt
  ? RAGAlt.getSellerResponse
  : RAG.getSellerResponse;

export const getSellerResponseSimple = useAlt
  ? RAGAlt.getSellerResponseSimple
  : RAG.getSellerResponseSimple;

export const getBuyerInitialMessage = useAlt
  ? RAGAlt.getBuyerInitialMessage
  : RAG.getBuyerInitialMessage;

export const getPatternAnalysisSuggestions = useAlt
  ? RAGAlt.getPatternAnalysisSuggestions
  : RAG.getPatternAnalysisSuggestions;

export const getSuggestionDetails = useAlt
  ? RAGAlt.getSuggestionDetails
  : RAG.getSuggestionDetails;

// Export translation, allowing alt override
export const translateText = useAlt
  ? RAGAlt.translateText
  : RAG.translateText;
