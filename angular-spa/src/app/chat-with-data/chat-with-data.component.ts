// Required for Angular
import { Component, OnInit, NgModule } from '@angular/core';
import { CommonModule } from '@angular/common';
// Required for MSAL
import { MsalBroadcastService, MsalService } from '@azure/msal-angular';

// Required for Angular multi-browser support
import { EventMessage, EventType, AuthenticationResult } from '@azure/msal-browser';

// Required for RJXS observables
import { filter } from 'rxjs/operators';
import { AiChatService } from '../aichat.service';
import { FormsModule } from '@angular/forms';

interface ChatMessage {
  sender: 'sent' | 'received';
  content: string;
}

@Component({
  selector: 'app-chat-with-data',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './chat-with-data.component.html',
  styleUrl: './chat-with-data.component.css'
})


export class ChatWithDataComponent {
  messages: ChatMessage[] = [];
  userInput: string = '';

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
      sender: 'sent',
      content: 'Hello! How are you?'
    });
    this.messages.push({
      sender: 'received',
      content: "I'm good, thank you! How about you?"
    });

  }

  click(){
    console.log("click");
    this.aiChatService.getChatResponse([{ role: "user", content: "Hello" }]);
    
  }

}
