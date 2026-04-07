import { Configuration, PopupRequest } from "@azure/msal-browser";

// Configurable via environment variables or hardcoded for POC
export const msalConfig: Configuration = {
    auth: {
        clientId: "YOUR_CLIENT_ID_HERE", // A REMPLACER par l'ID Client Azure
        authority: "https://login.microsoftonline.com/YOUR_TENANT_ID_HERE", // A REMPLACER par l'ID Tenant
        redirectUri: "http://localhost:5173", // Doit correspondre à la config Azure
    },
    cache: {
        cacheLocation: "sessionStorage", // This configures where your cache will be stored
        storeAuthStateInCookie: false, // Set this to "true" if you are having issues on IE11 or Edge
    },
};

// Add scopes here for ID token to be used at Microsoft identity platform endpoints.
export const loginRequest: PopupRequest = {
    scopes: ["User.Read"]
};
