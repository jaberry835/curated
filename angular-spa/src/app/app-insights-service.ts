import { Injectable } from "@angular/core";
import { ApplicationInsights } from "@microsoft/applicationinsights-web";
import { environment } from "../environments/environment";
@Injectable({
  providedIn: "root",
})
export class AppInsightsService {
  private appInsights: ApplicationInsights;

  constructor() {
    this.appInsights = new ApplicationInsights({
      config: {
        instrumentationKey: environment.insightsKey, // Replace with your Azure App Insights key
      },
    });
    this.appInsights.loadAppInsights();
  }

  logCustomEvent(eventName: string, properties?: { [key: string]: any }) {
    this.appInsights.trackEvent({ name: eventName, properties });
  }
}
