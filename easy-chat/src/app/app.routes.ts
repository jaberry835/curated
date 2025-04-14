import { Routes } from '@angular/router';
import { FailedComponent } from './failed/failed.component';
import { HomeComponent } from './home/home.component';
import { ProfileComponent } from './profile/profile.component';
import { MsalGuard } from '@azure/msal-angular';
import { ChatWithDataComponent } from './chat-with-data/chat-with-data.component';
import { DocViewerComponent } from './document-viewer/document-viewer.component';

export const routes: Routes = [
  {
    path: 'profile',
    component: ProfileComponent,
    canActivate: [MsalGuard],
  },
  {
    path: '',
    component: HomeComponent,
  },
  {
    path: 'login-failed',
    component: FailedComponent,
  },
  {
    path:'chat',
    component: ChatWithDataComponent,
    canActivate: [MsalGuard],
  },
  { path: 'doc-viewer', component: DocViewerComponent },

];
