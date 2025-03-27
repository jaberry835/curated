// Required for Angular
import { Component, OnInit, NgModule, ViewChild, ElementRef } from '@angular/core';
import { CommonModule } from '@angular/common';
// Required for MSAL
import { MsalBroadcastService, MsalService } from '@azure/msal-angular';

// Required for Angular multi-browser support
import { EventMessage, EventType, AuthenticationResult } from '@azure/msal-browser';

// Required for RJXS observables
import { filter } from 'rxjs/operators';
import { AiChatService } from '../aichat.service';
import { FormsModule } from '@angular/forms';
import { MarkdownModule } from 'ngx-markdown';
interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

@Component({
  selector: 'app-chat-with-data',
  standalone: true,
  imports: [CommonModule, FormsModule, MarkdownModule],
  templateUrl: './chat-with-data.component.html',
  styleUrl: './chat-with-data.component.css'
})


export class ChatWithDataComponent {
  messages: ChatMessage[] = [];
  userInput: string = '';
  @ViewChild('chatContainer') chatContainer!: ElementRef;
 
  constructor(
    private authService: MsalService,
    private msalBroadcastService: MsalBroadcastService,
    private aiChatService: AiChatService
    //   private AiChatService: AiChatService
  ) { }

  // Subscribe to the msalSubject$ observable on the msalBroadcastService
  // This allows the app to consume emitted events from MSAL
  ngOnInit(): void {
    this.msalBroadcastService.msalSubject$
      .pipe(
        filter((msg: EventMessage) => msg.eventType === EventType.LOGIN_SUCCESS),
      )
      .subscribe((result: EventMessage) => {
        const payload = result.payload as AuthenticationResult;
        this.authService.instance.setActiveAccount(payload.account);
      });

    // Initialize with some default messages.
    this.messages.push({
      role: 'assistant',
      content: 'Hello! I am chat bot on your data?'
    });


  }


  async click() {
    console.log("click");
    this.messages.push({
      role: 'user',
      content: this.userInput
    });
    
    var response = await this.aiChatService.getChatResponseStreaming([{ role: "user", content: this.userInput }]);
    this.userInput = '';
    // handle the response 
    let txtresponse = "";
    this.scrollToBottom();
    for await (const chunk of response) {
      for (const choice of chunk.choices) {
        const newText = choice.delta.content;
        if (!!newText) {
          console.log('gathering response');
          txtresponse += newText;
          console.log(newText);
        }
      }
    }
    // Initialize with some default messages.
    this.messages.push({
      role: 'assistant',
      content: txtresponse
    });

      
    this.scrollToBottom();
   
  }
  onEnter(): void {
   
    this.click();
  }

  // Scroll to the bottom of the chat container
  private scrollToBottom(): void {
    if (this.chatContainer) {
      this.chatContainer.nativeElement.scroll({
        top: this.chatContainer.nativeElement.scrollHeight,
        behavior: 'smooth' // Enables smooth scrolling
      });
    }
  }

}
