import React, { useState } from 'react';
import { Allotment } from 'allotment';
import ConversationPanel from './components/ConversationPanel';
import CopilotPanel from './components/CopilotPanel';
import { Message } from './types/conversation';
import {
  getBuyerInitialMessage,
  getSellerResponse,
  translateText
} from './services';
import 'allotment/dist/style.css';
import './App.css';

// Expanded buyer options list
const buyerOptions = [
  'ShadowWolf', 'LunarShopper', 'MoonBuyerX', 'CryptoCollector',
  'StellarShopper', 'GalaxyBuyer', 'NebulaNomad', 'OrbitTrader',
  'CometCollector', 'AstroAdmirer'
];
// Seller options for random selection
const sellerOptions = [
  'SilverHawk', 'GoldenFalcon', 'CrimsonFox', 'EmeraldEagle',
  'AzureDragon', 'BronzeBear', 'RubyRaven', 'ObsidianOwl',
  'TitaniumTiger', 'CopperCobra'
];
// Language options for seller communication
const languageOptions = ['English', 'Spanish', 'Russian', 'Chinese'];

function App() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isBotTyping, setIsBotTyping] = useState(false);
  // Language selection with default English
  const [selectedLanguage, setSelectedLanguage] = useState(languageOptions[0]);
  // Randomize buyer selection on initial load and allow changes
  const [selectedBuyer, setSelectedBuyer] = useState(() => {
    const idx = Math.floor(Math.random() * buyerOptions.length);
    return buyerOptions[idx];
  });
  // Randomize seller name on initial load
  const [selectedSeller] = useState(() => {
    const idx = Math.floor(Math.random() * sellerOptions.length);
    return sellerOptions[idx];
  });
  const [productDesc, setProductDesc] = useState('');
  const [started, setStarted] = useState(false);
  // Draft message state lifted for action insertion
  const [draftMessage, setDraftMessage] = useState('');

  const initiateConversation = async () => {
    if (!productDesc.trim()) return;
    setMessages([]);
    setIsBotTyping(true);
    setStarted(true);
    const initialText = await getBuyerInitialMessage(selectedBuyer, productDesc);
    // Translate buyer's initial message if needed
    let displayBuyerMsg = initialText;
    if (selectedLanguage !== 'English') {
      const native = await translateText(initialText, selectedLanguage);
      displayBuyerMsg = `${native}\n\n(English: ${initialText})`;
    }
    const buyerMsg: Message = {
      turn_order: 1,
      timestamp: new Date().toISOString(),
      role: 'Buyer',
      handle: selectedBuyer,
      message: displayBuyerMsg,
      negotiation_stage: 'initiation',
      coded_language: false,
      security_flags: { encrypted: false, pgp_key_exchanged: false },
      payment_details: null
    };
    setMessages([buyerMsg]);

    // Include only the buyer's initial message in history
    const reply = await getSellerResponse(selectedSeller, selectedBuyer, productDesc, initialText, [buyerMsg]);
    // Translate seller's English response to selected language if needed
    let displayReply = reply;
    if (selectedLanguage !== 'English') {
      const native = await translateText(reply, selectedLanguage);
      displayReply = `${native}\n\n(English: ${reply})`;
    }
    const sellerMsg: Message = {
      turn_order: 2,
      timestamp: new Date().toISOString(),
      role: 'Seller',
      handle: selectedSeller, // use dynamic seller name
      message: displayReply,
      negotiation_stage: 'specification',
      coded_language: false,
      security_flags: { encrypted: false, pgp_key_exchanged: false },
      payment_details: null
    };
    setMessages([buyerMsg, sellerMsg]);
    setIsBotTyping(false);
  };

  const handleSendMessage = async (messageText: string) => {
    // Determine negotiation stage based on buyer message content
    const text = messageText.toLowerCase();
    const stage = messages.length === 0
      ? 'initiation'
      : text.match(/\b(payment|wallet|transaction)\b/)  ? 'payment'
      : text.match(/\b(finalize|confirm|complete)\b/)     ? 'finalization'
      : 'specification';
    // Create and display buyer message
    // Translate buyer message
    let displayBuyer = messageText;
    if (selectedLanguage !== 'English') {
      const native = await translateText(messageText, selectedLanguage);
      displayBuyer = `${native}\n\n(English: ${messageText})`;
    }
    const newMessage: Message = {
      turn_order: messages.length + 1,
      timestamp: new Date().toISOString(),
      role: 'Buyer',
      handle: selectedBuyer,
      message: displayBuyer,
      negotiation_stage: stage,
      coded_language: false,
      security_flags: { encrypted: true, pgp_key_exchanged: true },
      payment_details: null
    };

    setMessages(prev => [...prev, newMessage]);
    setIsBotTyping(true);

    // Clear draft message after send
    setDraftMessage('');
    try {
      // Pass full conversation history including the new buyer message
      const history = [...messages, newMessage];
      const botReply = await getSellerResponse(selectedSeller, selectedBuyer, productDesc, messageText, history);
      // Translate seller's response
      let sellerDisplay = botReply;
      if (selectedLanguage !== 'English') {
        const native = await translateText(botReply, selectedLanguage);
        sellerDisplay = `${native}\n\n(English: ${botReply})`;
      }
      const sellerMessage: Message = {
        turn_order: messages.length + 2,
        timestamp: new Date().toISOString(),
        role: 'Seller',
        handle: selectedSeller, // dynamic seller
        message: sellerDisplay,
        negotiation_stage: stage,
        coded_language: false,
        security_flags: { encrypted: true, pgp_key_exchanged: true },
        payment_details: null
      };
      setMessages(prev => [...prev, sellerMessage]);
    } catch (error) {
      console.error('Error fetching seller response:', error);
    } finally {
      setIsBotTyping(false);
    }
  };

  return (
    <div className="App">
      <header className="App-header">
        <h1>Azure AI Negotiation Assistant Demo</h1>
        <button
          className="reset-btn"
          onClick={() => window.location.reload()}
        >
          New Conversation
        </button>
      </header>
      <div className="App-content">
        <Allotment defaultSizes={[60, 40]}>
          <Allotment.Pane minSize={300}>
            <ConversationPanel
              messages={messages}
              isBotTyping={isBotTyping}
              onSendMessage={handleSendMessage}
              started={started}
              draftMessage={draftMessage}
              setDraftMessage={setDraftMessage}
              sellerHandle={selectedSeller} // pass dynamic seller
            />
          </Allotment.Pane>
          <Allotment.Pane minSize={250}>
            <CopilotPanel
                buyerOptions={buyerOptions}
                selectedBuyer={selectedBuyer}
                setSelectedBuyer={setSelectedBuyer}
                languageOptions={languageOptions}
                selectedLanguage={selectedLanguage}
                setSelectedLanguage={setSelectedLanguage}
                productDesc={productDesc}
                setProductDesc={setProductDesc}
                initiateConversation={initiateConversation}
                started={started}
                messages={messages}
                setDraftMessage={setDraftMessage}
               />
             </Allotment.Pane>
        </Allotment>
      </div>
    </div>
  );
}

export default App;
