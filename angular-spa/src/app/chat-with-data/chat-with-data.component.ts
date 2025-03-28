// Required for Angular
import { Component, OnInit, NgModule, ViewChild, ElementRef, HostListener } from '@angular/core';
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
import { UnicodeDecoderPipe } from '../pipes/unicodeDecoder';
import { DomSanitizer } from '@angular/platform-browser';

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface PreviewFileType {
  title: string;        // Title of the file
  filepath: string;     // Filepath or URL to the file
  preview: string;
}

@Component({
  selector: 'app-chat-with-data',
  standalone: true,
  imports: [CommonModule, FormsModule, MarkdownModule, UnicodeDecoderPipe],
  templateUrl: './chat-with-data.component.html',
  styleUrl: './chat-with-data.component.css'
})


export class ChatWithDataComponent {
  messages: ChatMessage[] = [];
  chatCunks: any[] = [];
  userInput: string = '';
  @ViewChild('chatContainer') chatContainer!: ElementRef;

  pFile: PreviewFileType = { title: '', filepath: '', preview: '' };
  // @ts-ignore

  constructor(
    private authService: MsalService,
    private msalBroadcastService: MsalBroadcastService,
    private aiChatService: AiChatService,
    private domSanitizer: DomSanitizer
    //   private AiChatService: AiChatService
  ) {

  }

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
      content: 'Hello! I am chat bot that works on your data, ask me questions of your data collection!'
    });

  }

  ngAfterViewChecked() {
    this.scrollToBottom();
  }

  async click() {
    this.messages.push({
      role: 'user',
      content: this.userInput
    });



    await this.aiChatService.getChatResponse([{ role: "user", content: this.userInput }]).then((airesponse) => {
      this.userInput = '';
      //console.log(txtresponse);
      this.chatCunks.push(airesponse);
      // @ts-ignore
      let txt = this.buildCitationLink(airesponse.choices[0].message.content, airesponse.id)
      console.log(txt);
      this.messages.push({
        role: 'assistant',
        // @ts-ignore
        content: txt
      });
    }).catch((err) => {
      console.log(err);
    });
    this.scrollToBottom();
  }

  buildCitationLink(text: string, id: string): string {
    if (!text) {
      return text; // Return original text if null or empty
    }

    let newtxt = text.replace(/\[doc(\d+)\]/g, (match, docId) => {
      // Replace [docX] with a clickable link
      return `<a href="#/chat/${docId}/${id}">[${docId}]</a>`;
    });

    return newtxt;
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

  @HostListener('document:click', ['$event'])
  handleClick(event: Event): void {
    event.preventDefault();
    const target = event.target as HTMLElement;
    console.log(target);
    const href = target.getAttribute('href');
    if (href) {
      // Extract parameters from the URL fragment
      const fragment = href.split('#/chat')[1]; // Remove the '#'
      const parts = fragment.split('/');
      const docidRef = parts[1]; // Example: '1'
      const messageidRef = parts[2]; // Example: 'b628eeaa-818c-434f-a553-9621e01cd022'

      console.log('Parameter 1:', docidRef);
      console.log('Parameter 2:', messageidRef);
      this.showCitation(docidRef, messageidRef); // Call the function with the extracted parameters
    }

  }

  showCitation(docId: string, messageId: string): void {
    console.log('Citation clicked:', docId, messageId);

    console.log(this.chatCunks.find(x => x.id == messageId));
    let item = this.chatCunks.find(x => x.id == messageId).choices[0].message.context.citations[docId];
    let txt =item.content;
    this.pFile.preview = item.content;
    this.pFile.filepath = item.filepath;
    this.pFile.title = item.title;

    console.log(txt);
    // Handle the citation click event here
  }
  // Function to sanitize the HTML content
}
