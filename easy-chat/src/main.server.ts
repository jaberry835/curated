// src/main.server.ts
import 'zone.js/node';
import { enableProdMode } from '@angular/core';
import { bootstrapApplication } from '@angular/platform-server';
import { AppComponent } from './app/app.component';

// If in production mode (adjust as needed)
enableProdMode();

// Bootstrap your standalone root component on the server:
bootstrapApplication(AppComponent)
  .catch((err: any) => console.error(err));
