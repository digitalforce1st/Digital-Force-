import { NextResponse } from 'next/server';

export const runtime = 'edge';

export async function GET(request: Request, { params }: { params: Promise<{ path: string[] }> }) {
  const resolvedParams = await params;
  const path = resolvedParams.path;
  
  const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
  const targetUrl = `${API_BASE}/media/${path.join('/')}`;
  
  try {
    const response = await fetch(targetUrl, {
      headers: {
        'ngrok-skip-browser-warning': 'true'
      }
    });
    
    if (!response.ok) {
      return new NextResponse('Error fetching media', { status: response.status });
    }
    
    const buffer = await response.arrayBuffer();
    
    const headers = new Headers();
    headers.set('Content-Type', response.headers.get('Content-Type') || 'application/octet-stream');
    headers.set('Cache-Control', 'public, max-age=86400');
    
    return new NextResponse(buffer, { headers });
  } catch (error) {
    console.error('Proxy proxy media error:', error);
    return new NextResponse('Internal Proxy Error', { status: 500 });
  }
}
