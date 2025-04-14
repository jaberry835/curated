import { Component } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { NgxDocViewerModule } from 'ngx-doc-viewer';

@Component({
  selector: 'app-doc-viewer',
  standalone: true,
  imports: [NgxDocViewerModule],
  templateUrl: './document-viewer.component.html',
  styleUrls: ['./document-viewer.component.css'] 
})
export class DocViewerComponent {

  //docUrl: string | null = null;
  docUrl: string = 'https://cors-anywhere.herokuapp.com/https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf';
  constructor(private route: ActivatedRoute) {}

  ngOnInit(): void {
    // Read the document URL from the query parameters (e.g., ?docUrl=https://example.com/doc.docx)
   // this.docUrl = this.route.snapshot.queryParamMap.get('docUrl');
  }
}
