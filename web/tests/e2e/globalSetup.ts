import { startStubApi } from './stubApi';

/** One stub API for the whole run, where the preview server's proxy sends API paths. */
export default async function globalSetup(): Promise<() => Promise<void>> {
  const api = await startStubApi(Number(process.env.BK_E2E_API_PORT));
  return api.close;
}
