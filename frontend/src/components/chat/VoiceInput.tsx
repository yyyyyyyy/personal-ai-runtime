import { useState, useRef, useCallback } from "react";
import { Mic, MicOff } from "lucide-react";

declare global {
  interface Window {
    SpeechRecognition?: new () => SpeechRecognition;
    webkitSpeechRecognition?: new () => SpeechRecognition;
  }
}

interface SpeechRecognition {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onresult: (event: SpeechRecognitionEvent) => void;
  onerror: (event: SpeechRecognitionErrorEvent) => void;
  onend: () => void;
  start: () => void;
  stop: () => void;
  abort: () => void;
}

interface SpeechRecognitionEvent {
  results: SpeechRecognitionResultList;
}

interface SpeechRecognitionResultList {
  [index: number]: SpeechRecognitionResult;
  length: number;
}

interface SpeechRecognitionResult {
  [index: number]: SpeechRecognitionAlternative;
  isFinal: boolean;
  length: number;
}

interface SpeechRecognitionAlternative {
  transcript: string;
  confidence: number;
}

interface SpeechRecognitionErrorEvent {
  error: string;
}

function getSpeechRecognition(): SpeechRecognition | null {
  const SpeechRecognitionCtor = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognitionCtor) return null;
  const rec = new SpeechRecognitionCtor();
  rec.continuous = false;
  rec.interimResults = true;
  rec.lang = "zh-CN";
  return rec;
}

function speak(text: string) {
  if (typeof speechSynthesis === "undefined") return;
  speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = "zh-CN";
  utterance.rate = 1.1;
  utterance.pitch = 1.0;
  speechSynthesis.speak(utterance);
}

interface VoiceInputProps {
  onTranscript: (text: string) => void;
  disabled?: boolean;
}

export default function VoiceInput({ onTranscript, disabled }: VoiceInputProps) {
  const [isListening, setIsListening] = useState(false);
  const [isSupported, setIsSupported] = useState(true);
  const [interimText, setInterimText] = useState("");
  const recRef = useRef<SpeechRecognition | null>(null);

  const startListening = useCallback(() => {
    const rec = getSpeechRecognition();
    if (!rec) {
      setIsSupported(false);
      return;
    }
    recRef.current = rec;
    rec.onresult = (event: SpeechRecognitionEvent) => {
      let finalTranscript = "";
      let interimTranscript = "";
      for (let i = event.results.length - 1; i >= 0; i--) {
        const result = event.results[i];
        if (result.isFinal) {
          finalTranscript = result[0].transcript + finalTranscript;
        } else {
          interimTranscript = result[0].transcript + interimTranscript;
        }
      }
      setInterimText(interimTranscript);
      if (finalTranscript) {
        onTranscript(finalTranscript.trim());
        rec.stop();
      }
    };
    rec.onerror = (e: SpeechRecognitionErrorEvent) => {
      setIsListening(false);
      if (e.error === "not-allowed") setIsSupported(false);
    };
    rec.onend = () => {
      setIsListening(false);
      setInterimText("");
    };
    try {
      rec.start();
      setIsListening(true);
    } catch {
      setIsSupported(false);
    }
  }, [onTranscript]);

  const stopListening = useCallback(() => {
    recRef.current?.abort();
    setIsListening(false);
    setInterimText("");
  }, []);

  if (!isSupported) return null;

  return (
    <div className="flex items-center gap-1">
      {interimText && (
        <span className="text-xs text-emerald-400 animate-pulse max-w-40 truncate">
          {interimText}
        </span>
      )}
      <button
        type="button"
        onClick={isListening ? stopListening : startListening}
        disabled={disabled}
        className={`p-1.5 rounded-lg transition-colors ${
          isListening
            ? "bg-red-600/20 text-red-400 hover:bg-red-600/30"
            : "text-gray-500 hover:text-emerald-400 hover:bg-emerald-600/10"
        } disabled:opacity-30`}
        title={isListening ? "停止录音" : "语音输入"}
      >
        {isListening ? <MicOff size={16} /> : <Mic size={16} />}
      </button>
    </div>
  );
}

export { speak };
