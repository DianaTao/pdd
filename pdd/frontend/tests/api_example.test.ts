import { api } from '@/api';

/**
 * Example demonstrating how to use the PDDApiClient.
 * This example mocks the server response and shows how to fetch server status.
 *
 * Requirements:
 * - PDDApiClient relies on fetch() and WebSocket() which are mocked here for standalone execution.
 */
async function main() {
  console.log('=== PDD Frontend API Client Example ===');
  console.log('');

  // Mock global fetch
  // @ts-ignore
  global.fetch = async (url: string, options?: RequestInit) => {
    const endpoint = url.toString();
    console.log(`[MOCK] Request: ${options?.method || 'GET'} ${endpoint}`);

    if (endpoint.endsWith('/api/v1/status')) {
      return {
        ok: true,
        json: async () => ({
          version: '1.0.0-beta',
          project_root: '/workspaces/pdd',
          uptime_seconds: 12345,
          active_jobs: 2,
          connected_clients: 5
        })
      };
    }

    if (endpoint.endsWith('/api/v1/auth/status')) {
      return {
        ok: true,
        json: async () => ({
          authenticated: true,
          cached: true,
          expires_at: Date.now() + 3600000
        })
      };
    }

    return {
      ok: true,
      json: async () => ({ success: true })
    };
  };

  // Mock global WebSocket
  // @ts-ignore
  global.WebSocket = class MockWebSocket {
    onmessage: any = null;
    onerror: any = null;
    onclose: any = null;
    readyState = 1; // OPEN

    constructor(url: string) {
      console.log(`[MOCK] WebSocket connecting to: ${url}`);
      // Simulate a message after a short delay
      setTimeout(() => {
        if (this.onmessage) {
          this.onmessage({
            data: JSON.stringify({
              type: 'stdout',
              data: 'Hello from mock job stream!'
            })
          });
        }
      }, 10);
    }

    send(data: string) {
      console.log(`[MOCK] WebSocket send: ${data}`);
    }

    close() {
      console.log('[MOCK] WebSocket closed');
      if (this.onclose) this.onclose();
    }
  };

  try {
    // 1. Get Server Status
    console.log('Fetching server status...');
    const status = await api.getStatus();
    console.log(`Server Version: ${status.version}`);
    console.log(`Project Root: ${status.project_root}`);
    console.log('');

    // 2. Check Auth Status
    console.log('Checking authentication...');
    const auth = await api.getAuthStatus();
    console.log(`Authenticated: ${auth.authenticated}`);
    console.log('');

    // 3. Demonstrate WebSocket connection
    console.log('Connecting to job stream...');
    const ws = api.connectToJobStream('job-123', {
      onStdout: (text) => console.log(`Job stdout: ${text}`),
      onComplete: (success) => console.log(`Job completed: ${success}`),
      onClose: () => console.log('Job stream closed')
    });

    // Allow some time for the mock message to arrive
    await new Promise(resolve => setTimeout(resolve, 50));
    ws.close();

    console.log('');
    console.log('Example finished successfully.');
  } catch (error: any) {
    console.error('Example failed with error:', error.message);
    process.exit(1);
  }
}

// Run the example
main();
