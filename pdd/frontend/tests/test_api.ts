import { describe, it, expect, vi, beforeEach } from 'vitest';
import { api } from '../api';

describe('PDDApiClient', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
    // @ts-ignore
    vi.stubGlobal('WebSocket', vi.fn().mockImplementation(function() {
      return {
        send: vi.fn(),
        close: vi.fn(),
        readyState: 1,
        onmessage: null,
        onerror: null,
        onclose: null
      };
    }));
  });

  it('should fetch server status correctly', async () => {
    const mockStatus = {
      version: '1.2.3',
      project_root: '/tmp',
      uptime_seconds: 100,
      active_jobs: 0,
      connected_clients: 1
    };

    (global.fetch as any).mockResolvedValue({
      ok: true,
      json: async () => mockStatus
    });

    const status = await api.getStatus();
    expect(status).toEqual(mockStatus);
    expect(global.fetch).toHaveBeenCalledWith(expect.stringContaining('/api/v1/status'), expect.any(Object));
  });

  it('should handle API errors gracefully', async () => {
    (global.fetch as any).mockResolvedValue({
      ok: false,
      status: 500,
      statusText: 'Internal Server Error',
      json: async () => ({ detail: 'Something went wrong' })
    });

    await expect(api.getStatus()).rejects.toThrow('Something went wrong');
  });

  it('should execute a command and return a job handle', async () => {
    const mockHandle = {
      job_id: 'job-456',
      status: 'queued',
      created_at: new Date().toISOString()
    };

    (global.fetch as any).mockResolvedValue({
      ok: true,
      json: async () => mockHandle
    });

    const handle = await api.executeCommand({ command: 'test', args: { foo: 'bar' } });
    expect(handle).toEqual(mockHandle);
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/commands/execute'),
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ command: 'test', args: { foo: 'bar' } })
      })
    );
  });

  it('should connect to job stream WebSocket', () => {
    const callbacks = {
      onStdout: vi.fn(),
      onComplete: vi.fn()
    };

    const ws = api.connectToJobStream('job-123', callbacks);
    expect(global.WebSocket).toHaveBeenCalledWith(expect.stringContaining('/ws/jobs/job-123/stream'));
    expect(ws).toBeDefined();
  });

  it('should fetch and cache cloud URL', async () => {
    const mockCloudUrl = 'https://cloud.pdd.dev';
    (global.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ cloud_url: mockCloudUrl })
    });

    const url1 = await api.getCloudUrl();
    expect(url1).toBe(mockCloudUrl);

    // Second call should use cache
    const url2 = await api.getCloudUrl();
    expect(url2).toBe(mockCloudUrl);
    expect(global.fetch).toHaveBeenCalledTimes(1);
  });
});
