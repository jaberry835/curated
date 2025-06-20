// Types for the negotiation conversation demo
export interface SecurityFlags {
  encrypted: boolean;
  pgp_key_exchanged: boolean;
}

export interface PaymentDetails {
  escrow_id?: string;
  crypto_wallet_requested?: boolean;
  crypto_wallet?: string;
  transaction_id?: string;
  amount?: string;
  transaction_status?: string;
  delivery_info?: string;
}

export interface Message {
  turn_order: number;
  timestamp: string;
  role: "Buyer" | "Seller";
  handle: string;
  message: string;
  negotiation_stage: string;
  coded_language: boolean;
  security_flags: SecurityFlags;
  payment_details: PaymentDetails | null;
}

export interface ConversationData {
  conversation_id: string;
  turns: Message[];
  outcome: "successful" | "failed" | "in_progress";
}

export interface Suggestion {
  id: string;
  type: "pattern_analysis" | "negotiation_tactic" | "risk_assessment" | "next_move";
  title: string;
  content: string;
  confidence: number; // Confidence score from 0.0 to 1.0
  rank: number;       // Suggestion rank, 1 = highest priority
  next_response_area: string; // Logical next area the buyer should address
  action_items: string[];
}

export interface AzureSearchResult {
  conversationId: string;
  similarity: number;
  context: string;
  recommendations: string[];
}

export interface OpenAIResponse {
  suggestions: Suggestion[];
  analysis: string;
  confidence: number;
}
