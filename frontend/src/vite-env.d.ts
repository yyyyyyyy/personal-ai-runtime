/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_AUTH_TOKEN?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

declare const __API_HOST__: string;
declare const __API_PORT__: string;

declare module "remark-breaks";
