
import { AzureOpenAI, OpenAI } from "openai";
import { Injectable } from '@angular/core';
import "@azure/openai/types";
import { retryWhen } from "rxjs";
//import {  ChatCompletionCreateParamsStreaming } from "openai/resources/chat/completions";
import { environment } from "../environments/environment";

interface ChatMessage {
  role: "system" | "user" | "assistant";
  content: string;
}

@Injectable({
  providedIn: 'root'
})


export class AiChatService {
  private client: AzureOpenAI;
  // Your deployment ID—often a model like "gpt-35-turbo"
  private deploymentId = "gpt-4o";
  // Replace with your resource's endpoint and key
  endpoint = environment.aiEndpoint; //"https://jb-ai-test.openai.azure.com";
  apiKey = environment.aiKey;
  apiVersion = environment.apiVersion;// "2024-05-01-preview";
  // Your Azure Cognitive Search endpoint, and index name
  azureSearchEndpoint = environment.azureSearchEndpoint; //"https://jb-ai-test-search.search.windows.net";
  azureSearchIndexName = environment.azureSearchIndexName; //"runtestidx"
  azureSearchKey = environment.azureSearchKey;
  //https://jb-ai-test.openai.azure.com/openai/deployments/gpt-4o/chat/completions?api-version=2024-02-15-preview
  constructor() {
    this.client = new AzureOpenAI({
      endpoint: this.endpoint,
      apiKey: this.apiKey,
      apiVersion: this.apiVersion,
      deployment: this.deploymentId,
      dangerouslyAllowBrowser: true
    });
  }
  /**
   * Calls Azure OpenAI to get a chat completion based on the conversation history.
   * @param messages An array of messages in the format required by Azure OpenAI.
   * @returns A Promise that resolves to the assistant’s reply.
   */
  async getChatResponse(messages: ChatMessage[]) {
    try {
      const params = {};
      // @ts-ignore
      const response = await this.client.chat.completions.create({
        model: "gpt-4o",
        stream: true,
        messages: [
          {
            role: "user",
            content: "Tell me something from the news from my data"
          }
        ],

        max_tokens: 550,
        "data_sources": [
    {
      "type": "azure_search",
      "parameters": {
        "endpoint": environment.azureSearchEndpoint,
        "index_name": "runtestidx",
        "semantic_configuration": "default",
        "query_type": "vector_semantic_hybrid",
        "fields_mapping": {},
        "in_scope": true,
        "role_information": "",
        "filter": null,
        "strictness": 3,
        "top_n_documents": 11,
        "authentication": {
          "type": "api_key",
          "key": ""
        },
        "embedding_dependency": {
          "type": "gpt-4o",
          "deployment_name": "text-embedding-ada-002"
        },
        "key": environment.azureSearchKey,
        "indexName": environment.azureSearchIndexName
      }
    }
  ],

      });

      let txtresponse = "";
      for await (const chunk of response) {
        for (const choice of chunk.choices) {
          const newText = choice.delta.content;
          if (!!newText) {

            txtresponse += newText;
          }
        }
      }
      console.log(txtresponse)
      return txtresponse;
    }
    catch (err) {
      return 'failed'
    }
  }
}
/*
await this.client.chat.completions.create({
  messsages: [
    {
      role: "user",
      content: "tell me about the news in my data",
    },
  ],
  max_tokens: 128,
});*/
//   await this.client.chat.completions.create(params);
/*
        body:{
          messsages: [
            {
              role: "user",
              content: "tell me about the news in my data",
            },
          ],
          max_tokens: 128,
          model: "gpt-4o",
          data_sources: [
            {
              type: "azure_search",
              parameters: {
                endpoint: this.azureSearchEndpoint,
                index_name: this.azureSearchIndexName,
                authentication: {
                  type: "system_assigned_managed_identity",
                },
              },
            },
          ],
        });
    } catch (err) {
      console.error("Azure OpenAI error:", err);
      return "Error: Unable to get response";
    }*/

