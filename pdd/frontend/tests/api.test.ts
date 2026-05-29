import { describe, it, expect, vi, beforeEach } from 'vitest';
import { api } from '../api';

describe('PDDApiClient Cloud Requests (Issue #1152)', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
    // Mock internal requests
    (fetch as any).mockImplementation((url: string) => {
      if (url.includes('/api/v1/auth/jwt-token')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ jwt: 'fake-token' }),
        });
      }
      if (url.includes('/api/v1/config/cloud-url')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ cloud_url: 'https://fake-cloud.com' }),
        });
      }
      if (url.includes('/listSessions')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ sessions: [{ sessionId: '123' }] }),
        });
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({}),
      });
    });
  });

  it('listRemoteSessions uses cloudRequest with Bearer token and correct cloud URL', async () => {
    const sessions = await api.listRemoteSessions();
    
    expect(sessions).toHaveLength(1);
    expect(sessions[0].sessionId).toBe('123');
    
    // Verify cloud endpoint call
    expect(fetch).toHaveBeenCalledWith(
      'https://fake-cloud.com/listSessions',
      expect.objectContaining({
        headers: expect.objectContaining({
          'Authorization': 'Bearer fake-token',
          'Content-Type': 'application/json'
        })
      })
    );
  });

  it('submitRemoteCommand uses cloudRequest', async () => {
    await api.submitRemoteCommand({
      sessionId: '123',
      type: 'test',
      payload: {}
    });
    
    expect(fetch).toHaveBeenCalledWith(
      'https://fake-cloud.com/submitCommand',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({
          'Authorization': 'Bearer fake-token'
        })
      })
    );
  });
});
