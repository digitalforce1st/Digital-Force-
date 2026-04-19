"use client";

import React, { useState, useEffect, useRef } from "react";
import { Mic, Square, X, Loader2, Volume2, Waves } from "lucide-react";

export default function VoiceInterface() {
  const [isOpen, setIsOpen] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [status, setStatus] = useState<"idle" | "listening" | "processing" | "speaking" | "error">("idle");
  const [transcript, setTranscript] = useState("");
  const [agentReply, setAgentReply] = useState("");

  const wsRef = useRef<WebSocket | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const audioPlaybackRef = useRef<HTMLAudioElement | null>(null);

  // Initialize WebSocket connection when overlay opens
  useEffect(() => {
    if (isOpen && !wsRef.current) {
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      // Assuming backend runs on 8000 locally
      const wsUrl = `${protocol}//localhost:8000/api/voice/stream`;
      const ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        console.log("Voice WS Connected");
      };

      ws.onmessage = async (event) => {
        const data = JSON.parse(event.data);
        
        if (data.type === "stt") {
          setTranscript(data.text);
          setStatus("processing");
        } else if (data.type === "llm") {
          setAgentReply(data.text);
        } else if (data.type === "tts") {
          setStatus("speaking");
          // Play base64 audio
          const audioUrl = `data:audio/mp3;base64,${data.audio_b64}`;
          if (audioPlaybackRef.current) {
            audioPlaybackRef.current.src = audioUrl;
            audioPlaybackRef.current.play();
            audioPlaybackRef.current.onended = () => {
               setStatus("idle");
               // Optionally auto-start listening again here for continuous mode
            };
          }
        } else if (data.type === "error") {
          setStatus("error");
          console.error("Voice Hub Error:", data.message);
        }
      };

      ws.onclose = () => {
        console.log("Voice WS Disconnected");
        wsRef.current = null;
      };

      wsRef.current = ws;
    }

    // Cleanup on unmount or close
    return () => {
      if (!isOpen && wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [isOpen]);

  const startRecording = async () => {
    try {
      setTranscript("");
      setAgentReply("");
      setStatus("listening");
      
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      
      // Use standard webm for chunks
      const mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
        // Send to backend via WS
        if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
          wsRef.current.send(audioBlob);
          setStatus("processing");
        } else {
           setStatus("error");
        }
        
        // Stop all tracks
        if (streamRef.current) {
          streamRef.current.getTracks().forEach((track) => track.stop());
        }
      };

      mediaRecorder.start();
      setIsRecording(true);
    } catch (err) {
      console.error("Error accessing microphone:", err);
      setStatus("error");
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
    }
  };

  return (
    <>
      {/* Hidden Audio Element for TTS Playback */}
      <audio ref={audioPlaybackRef} className="hidden" />

      {/* Floating Action Button */}
      {!isOpen && (
        <button
          onClick={() => setIsOpen(true)}
          className="fixed bottom-6 right-6 p-4 rounded-full bg-blue-600 hover:bg-blue-500 text-white shadow-xl hover:shadow-2xl transition-all z-50 flex items-center justify-center ring-4 ring-blue-500/20 group"
          title="Voice Hub"
        >
          <Mic className="w-6 h-6 group-hover:scale-110 transition-transform" />
        </button>
      )}

      {/* Voice Interface Overlay */}
      {isOpen && (
        <div className="fixed bottom-6 right-6 w-96 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-2xl shadow-2xl flex flex-col z-50 overflow-hidden font-sans">
          
          {/* Header */}
          <div className="flex items-center justify-between p-4 border-b border-gray-100 dark:border-gray-800 bg-gray-50/50 dark:bg-gray-800/50">
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-blue-500 animate-pulse" />
              <span className="font-semibold text-sm text-gray-700 dark:text-gray-200">
                Agentic Voice Hub
              </span>
            </div>
            <button
              onClick={() => setIsOpen(false)}
              className="p-1 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-lg transition-colors"
            >
              <X className="w-4 h-4 text-gray-500" />
            </button>
          </div>

          {/* Conversation Area */}
          <div className="p-6 flex flex-col gap-4 min-h-[200px] max-h-[300px] overflow-y-auto">
            {transcript && (
              <div className="self-end bg-blue-100 dark:bg-blue-900/40 text-blue-900 dark:text-blue-100 p-3 rounded-2xl rounded-tr-sm text-sm max-w-[85%]">
                {transcript}
              </div>
            )}
            
            {agentReply && (
              <div className="self-start bg-gray-100 dark:bg-gray-800 text-gray-800 dark:text-gray-200 p-3 rounded-2xl rounded-tl-sm text-sm max-w-[85%] flex items-start gap-2 border border-gray-200 dark:border-gray-700/50">
                 {status === "speaking" && <Volume2 className="w-4 h-4 mt-0.5 text-blue-500 animate-pulse" />}
                 <span>{agentReply}</span>
              </div>
            )}
            
            {status === "processing" && (
              <div className="self-start text-xs text-gray-400 flex items-center gap-2 mt-2">
                <Loader2 className="w-3 h-3 animate-spin"/> Processing via Groq LPU...
              </div>
            )}
            
            {status === "idle" && !transcript && (
              <div className="text-center text-gray-400 text-sm mt-8">
                Ready. Press the microphone to speak.
              </div>
            )}
          </div>

          {/* Controls Footer */}
          <div className="p-4 border-t border-gray-100 dark:border-gray-800 bg-gray-50/50 dark:bg-gray-800/50 flex justify-center items-center">
            
            {status === "listening" && (
                <div className="absolute inset-x-0 bottom-20 flex justify-center pointer-events-none">
                    <Waves className="w-12 h-12 text-blue-500 opacity-50 animate-pulse" />
                </div>
            )}

            <button
              onClick={isRecording ? stopRecording : startRecording}
              disabled={status === "processing" || status === "speaking"}
              className={`
                p-4 rounded-full transition-all duration-300 shadow-lg relative
                ${isRecording 
                  ? "bg-red-500 hover:bg-red-600 ring-4 ring-red-500/30 scale-105" 
                  : "bg-blue-600 hover:bg-blue-500 ring-4 ring-transparent hover:ring-blue-500/20"}
                ${(status === "processing" || status === "speaking") ? "opacity-50 cursor-not-allowed scale-90 grayscale" : ""}
              `}
            >
              {isRecording ? (
                <Square className="w-6 h-6 text-white fill-current" />
              ) : (
                <Mic className="w-6 h-6 text-white" />
              )}
            </button>
          </div>
          
        </div>
      )}
    </>
  );
}
