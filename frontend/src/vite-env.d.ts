/// <reference types="vite/client" />

/** The frontend's build stamp (vite.config.ts): the package version and the build. */
declare const __APP_VERSION__: string;
declare const __APP_BUILD__: string;

declare module "*.module.css" {
  const classes: Readonly<Record<string, string>>;
  export default classes;
}
