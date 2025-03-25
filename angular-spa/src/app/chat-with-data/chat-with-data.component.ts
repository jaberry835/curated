// Required for Angular
import { Component, OnInit } from '@angular/core';

// Required for MSAL
import { MsalBroadcastService, MsalService } from '@azure/msal-angular';

// Required for Angular multi-browser support
import { EventMessage, EventType, AuthenticationResult } from '@azure/msal-browser';

// Required for RJXS observables
import { filter } from 'rxjs/operators';
import { AiChatService } from '../aichat.service';

@Component({
  selector: 'app-chat-with-data',
  standalone: true,
  imports: [],
  templateUrl: './chat-with-data.component.html',
  styleUrl: './chat-with-data.component.css'
})
export class ChatWithDataComponent {
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
  }

  click(){
    console.log("click");
    this.aiChatService.getChatResponse([{ role: "user", content: "Hello" }]);
    
  }

}
