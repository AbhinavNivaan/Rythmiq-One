/**
 * App Configuration
 * 
 * Centralized configuration for the React Native app.
 * Uses environment variables from app.json extra field.
 */

import Constants from 'expo-constants';

interface AppConfig {
  // API Configuration
  apiBaseUrl: string;
  apiTimeout: number;
  
  // Environment
  environment: 'development' | 'staging' | 'production';
  isDevelopment: boolean;
  isProduction: boolean;
  
  // Feature Flags
  features: {
    biometricAuth: boolean;
    offlineMode: boolean;
    analytics: boolean;
    crashReporting: boolean;
  };
  
  // Security
  sessionTimeoutMs: number;
  maxLoginAttempts: number;
  
  // Cache
  imageCacheMaxSizeMb: number;
  imageCacheMaxAgeDays: number;
  
  // App Info
  appName: string;
  appVersion: string;
  buildNumber: string;
}

// Get values from expo extra config or use defaults
const extra = Constants.expoConfig?.extra || {};

const environment = (extra.environment || 'development') as AppConfig['environment'];

const config: AppConfig = {
  // API Configuration
  apiBaseUrl: extra.apiBaseUrl || 'http://localhost:8000',
  apiTimeout: extra.apiTimeout || 30000,
  
  // Environment
  environment,
  isDevelopment: environment === 'development',
  isProduction: environment === 'production',
  
  // Feature Flags
  features: {
    biometricAuth: extra.enableBiometric ?? true,
    offlineMode: extra.enableOffline ?? false,
    analytics: environment === 'production',
    crashReporting: environment === 'production',
  },
  
  // Security
  sessionTimeoutMs: 30 * 60 * 1000, // 30 minutes
  maxLoginAttempts: 5,
  
  // Cache
  imageCacheMaxSizeMb: 100,
  imageCacheMaxAgeDays: 7,
  
  // App Info
  appName: Constants.expoConfig?.name || 'Rythmiq',
  appVersion: Constants.expoConfig?.version || '1.0.0',
  buildNumber: extra.buildNumber || '1',
};

// Environment-specific overrides — prefer EXPO_PUBLIC_API_URL baked in at build time
if (process.env.EXPO_PUBLIC_API_URL) {
  config.apiBaseUrl = process.env.EXPO_PUBLIC_API_URL;
}

// Validate required config
if (!config.apiBaseUrl) {
  console.warn('API_BASE_URL is not configured');
}

export default config;

// Named exports for convenience
export const {
  apiBaseUrl,
  apiTimeout,
  environment: appEnvironment,
  isDevelopment,
  isProduction,
  features,
  sessionTimeoutMs,
  appName,
  appVersion,
} = config;
