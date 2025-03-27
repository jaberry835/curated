
import { AzureOpenAI, OpenAI } from "openai";
import { Injectable } from '@angular/core';
import "@azure/openai/types";
import { retryWhen } from "rxjs";
//import {  ChatCompletionCreateParamsStreaming } from "openai/resources/chat/completions";
import { environment } from "../environments/environment";
import { PayloadData, updatePayload, UpdatePayloadOptions } from "./payload/payload-helper";

interface ChatMessage {
  role: "system" | "user" | "assistant";
  content: string;
}

const originalPayload: PayloadData = {
  "messages": [
    {
      "role": "user",
      "content": "tell me about some news from the dataset provided"
    }
  ],
  "temperature": 0.7,
  "top_p": 0.95,
  "max_tokens": 2500,
  "stop": null,
  "stream": true,
  "frequency_penalty": 0,
  "presence_penalty": 0,
  "data_sources": [
    {
      "type": "azure_search",
      "parameters": {
        "endpoint": environment.azureSearchEndpoint,
        "index_name": "runtestidx",
        "strictness": 3,
        "top_n_documents": 5,
        "in_scope": false,
        "semantic_configuration": "default",
        "query_type": "vector_semantic_hybrid",
        "embedding_dependency": {
          "type": "deployment_name",
          "deployment_name": "text-embedding-ada-002"
        },
        "fields_mapping": {},
        "authentication": {
          "type": "api_key",
          "key": environment.azureSearchKey
        }
      }
    }
  ]
}

@Injectable({
  providedIn: 'root'
})


export class AiChatService {
  private client: AzureOpenAI;
  // Your deployment ID—often a model like "gpt-35-turbo"
  private deploymentId = "gpt-4o";
  // Replace with your resource's endpoint and key
  endpoint = environment.aiEndpoint;
  apiKey = environment.aiKey;
  apiVersion = environment.apiVersion;
  azureSearchEndpoint = environment.azureSearchEndpoint;
  azureSearchIndexName = environment.azureSearchIndexName;
  azureSearchKey = environment.azureSearchKey;




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
      const options: UpdatePayloadOptions = {
        messages: messages,
        top_n_documents: 10,
        strictness: 3
      };
      let uPayload = updatePayload(originalPayload, options);
      console.log(uPayload)
      // @ts-ignore
      const response = await this.client.chat.completions.create(uPayload);


      let txtresponse = "";
      for await (const chunk of response) {
        for (const choice of chunk.choices) {
          const newText = choice.delta.content;
          if (!!newText) {
            console.log('gathering response');
            txtresponse += newText;
          }
        }
      }
      console.log('response gathered');
      //console.log(txtresponse)
      return txtresponse;
    }
    catch (err) {
      return 'failed'
    }
  }

  async getChatResponseStreaming(messages: ChatMessage[]): Promise<any> {
    try {
      const options: UpdatePayloadOptions = {
        messages: messages,
        top_n_documents: 10,
        strictness: 3
      };
      let uPayload = updatePayload(originalPayload, options);
      console.log(uPayload)
      // @ts-ignore
      const response = await this.client.chat.completions.create(uPayload);

      return response;


    }
    catch (err) {
      return null;
    }
  }

}

