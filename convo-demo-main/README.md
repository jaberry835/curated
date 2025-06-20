# AI Negotiation Demo

A React/TypeScript demo app showcasing a simulated negotiation between a buyer and seller using Azure AI Search (RAG) and Azure OpenAI (GPT-4o) with cryptocurrency pricing.

## Features
- Split-pane UI: left for conversation, right for AI copilot insights
- Dynamic RAG-powered buyer and seller responses
- Negotiation stages: initiation, specification, payment, finalization
- Crypto pricing (BTC/ETH) with live USD estimates
- AI-driven pattern analysis suggestions with clickable prompts
- Auto-scroll to latest messages
- Accessible controls and left-justified text

## Prerequisites
- Node.js (v16+) and npm installed
- Azure OpenAI resource with a deployed model
- Azure Cognitive Search index populated with relevant context documents

## Getting Started
1. Clone this repository:
   ```bash
   git clone https://github.com/your-org/ai-negotiation-demo.git
   cd ai-negotiation-demo
   ```
2. Copy the sample environment file and provide your Azure credentials:
   ```bash
   cp .env.sample .env
   # Edit .env and fill in your endpoint, API keys, and index name
   ```
3. Install dependencies:
   ```bash
   npm install
   ```
4. Run the development server:
   ```bash
   npm start
   ```
   The app will open at [http://localhost:3000](http://localhost:3000).

## Build for Production
```bash
npm run build
```
Bundle files are generated in the `build/` folder, ready for deployment.

## How It Works
1. **Initiation**: Select a buyer persona, describe a product, click "Initiate Conversation." The app generates an initial buyer message, then a seller reply via Azure OpenAI & Search.
2. **Chat**: Continue messaging in the left panel. The AI tracks negotiation stage and responds accordingly.
3. **AI Copilot**: The right panel analyzes conversation patterns and provides actionable suggestions. Click a suggested prompt to prefill the input box.
4. **Crypto Pricing**: All prices are quoted in BTC/ETH. When a crypto amount is mentioned, an estimated USD value appears above the AI panel.

## Next Steps
- Add live exchange rate lookup
- Expand suggestion tabs (tactics, risk, next moves)
- Integrate real payment workflows
- Deploy to Azure Static Web Apps or App Service

## License
MIT
