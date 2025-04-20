import { Component } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { NgxDocViewerModule } from 'ngx-doc-viewer';
import * as JSZip from 'jszip';
@Component({
  selector: 'app-doc-viewer',
  standalone: true,
  imports: [NgxDocViewerModule],
  templateUrl: './document-viewer.component.html',
  styleUrls: ['./document-viewer.component.css'] 
})
export class DocViewerComponent {

  //docUrl: string | null = null;
  docUrl: string = '';
  constructor(private route: ActivatedRoute) {}

  ngOnInit(): void {
    // Read the document URL from the query parameters (e.g., ?docUrl=https://example.com/doc.docx)
    this.docUrl = this.route.snapshot.queryParamMap.get('docUrl') || this.docUrl;
  }
  onError(event: any) {
    console.error("Error loading document:", event);
    alert("Failed to load the document. Please try again.");
  }
}
