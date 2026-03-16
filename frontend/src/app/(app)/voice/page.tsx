"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { apiFetch, apiInterviewStream } from "@/lib/api";
import ConversationImport from "./components/ConversationImport";

// --- Web Speech API types (browser globals not in default TS lib) ---

interface SpeechRecognitionEvent extends Event {
  results: SpeechRecognitionResultList;
  resultIndex: number;
}

interface SpeechRecognitionErrorEvent extends Event {
  error: string;
  message: string;
}

type SpeechRecognitionCtor = new () => SpeechRecognitionInstance;

interface SpeechRecognitionInstance extends EventTarget {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  start(): void;
  stop(): void;
  abort(): void;
  onresult: ((event: SpeechRecognitionEvent) => void) | null;
  onerror: ((event: SpeechRecognitionErrorEvent) => void) | null;
  onend: (() => void) | null;
}

declare global {
  interface Window {
    SpeechRecognition?: SpeechRecognitionCtor;
    webkitSpeechRecognition?: SpeechRecognitionCtor;
  }
}

// --- Types ---

interface StyleMarkers {
  vocabulary_tier: string;
  avg_sentence_length: string;
  sentence_variety: string;
  pacing_style: string;
  emotional_register: string;
  sensory_preference: string;
  dialogue_style: string;
  pov_tendency: string;
  tense_preference: string;
  humor_and_wit: string;
  figurative_language: string;
  structural_patterns: string;
  notable_patterns: string[];
  comparable_authors: string[];
  confidence_note: string;
}

interface AnalyzeResponse {
  session_id: string;
  style_markers: StyleMarkers;
}

interface InterviewMessage {
  role: "user" | "assistant";
  content: string;
}

interface LiteraryDNA {
  vocabulary_tier: string;
  sentence_rhythm: string;
  pacing_style: string;
  emotional_register: string;
  sensory_mode: string;
  dialogue_approach: string;
  pov_preference: string;
  tense_preference: string;
  humor_style: string;
  darkness_calibration: string;
  cognitive_style: {
    processing_mode: string;
    story_entry_point: string;
    revision_pattern: string;
    plotter_pantser: string;
  };
  notable_patterns: string[];
  comparable_authors: string[];
}

interface ProfileResult {
  profile_id: string;
  profile_name: string;
  literary_dna: LiteraryDNA;
  influences: {
    rhythm_from: string[];
    structure_from: string[];
    tone_from: string[];
    anti_influences: string[];
  };
  anti_slop: {
    personal_banned_words: string[];
    personal_banned_patterns: string[];
    cringe_triggers: string[];
    genre_constraints: string[];
  };
  voice_instruction: string;
  voice_summary: string;
}

type Step = 1 | 2 | 3 | 4 | 5;

// --- Thought block filter (safety net — backend strips these, catch any leaks) ---

const THOUGHT_BLOCK_RE = /<thought_process>[\s\S]*?<\/thought_process>/g;

/**
 * Strip <thought_process>...</thought_process> blocks from displayed text.
 * If an unclosed opening tag is present (block still arriving), hide
 * everything from the tag onward until the closing tag arrives.
 */
function stripThoughtBlocks(text: string): string {
  // Remove complete thought blocks
  let cleaned = text.replace(THOUGHT_BLOCK_RE, "");
  // If an unclosed <thought_process> remains, hide everything after it
  const openIdx = cleaned.indexOf("<thought_process>");
  if (openIdx !== -1) {
    cleaned = cleaned.substring(0, openIdx);
  }
  return cleaned;
}

// --- Main Component ---

export default function VoiceDiscoveryPage() {
  const router = useRouter();
  const [step, setStep] = useState<Step>(1);

  // Step 1 state
  const [writingSample, setWritingSample] = useState("");
  const [sampleContext, setSampleContext] = useState("");
  const [analyzing, setAnalyzing] = useState(false);
  const [analyzeError, setAnalyzeError] = useState("");

  // Step 2 state
  const [sessionId, setSessionId] = useState("");
  const [styleMarkers, setStyleMarkers] = useState<StyleMarkers | null>(null);
  const [conversationImportDone, setConversationImportDone] = useState(false);

  // Step 3 state
  const [messages, setMessages] = useState<InterviewMessage[]>([]);
  const [userInput, setUserInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [streamingText, setStreamingText] = useState("");
  const [questionNumber, setQuestionNumber] = useState(0);
  const [interviewComplete, setInterviewComplete] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Step 4 state
  const [profileName, setProfileName] = useState("My Voice");
  const [compiling, setCompiling] = useState(false);
  const [compileError, setCompileError] = useState("");

  // Step 5 state
  const [profile, setProfile] = useState<ProfileResult | null>(null);
  const [showVoiceInstruction, setShowVoiceInstruction] = useState(false);

  // Voice input state
  const [isRecording, setIsRecording] = useState(false);
  const [speechSupported, setSpeechSupported] = useState(false);
  const recognitionRef = useRef<SpeechRecognitionInstance | null>(null);

  const wordCount = writingSample.split(/\s+/).filter(Boolean).length;

  // Check Web Speech API support on mount
  useEffect(() => {
    const SpeechRecognition =
      window.SpeechRecognition || window.webkitSpeechRecognition;
    setSpeechSupported(!!SpeechRecognition);
  }, []);

  // Auto-scroll interview messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingText]);

  // --- Step 1: Analyze ---

  const handleAnalyze = async () => {
    setAnalyzing(true);
    setAnalyzeError("");
    try {
      const data = await apiFetch<AnalyzeResponse>(
        "/api/voice-discovery/analyze",
        {
          method: "POST",
          body: JSON.stringify({
            writing_sample: writingSample,
            sample_context: sampleContext,
          }),
        }
      );
      setSessionId(data.session_id);
      setStyleMarkers(data.style_markers);
      setStep(2);
    } catch (e) {
      setAnalyzeError(
        e instanceof Error ? e.message : "Analysis failed — please try again."
      );
    } finally {
      setAnalyzing(false);
    }
  };

  // --- Step 3: Interview ---

  const sendInterviewMessage = useCallback(
    async (message: string) => {
      if (streaming) return;
      setStreaming(true);
      setStreamingText("");

      if (message) {
        setMessages((prev) => [...prev, { role: "user", content: message }]);
      }
      setUserInput("");

      let accumulated = "";
      try {
        await apiInterviewStream(
          "/api/voice-discovery/interview",
          { session_id: sessionId, user_message: message },
          (token) => {
            accumulated += token;
            setStreamingText(stripThoughtBlocks(accumulated));
          },
          (doneData) => {
            // Final cleanup — strip any thought blocks from stored content
            const cleanContent = accumulated
              .replace(THOUGHT_BLOCK_RE, "")
              .trim();
            setMessages((prev) => [
              ...prev,
              { role: "assistant", content: cleanContent },
            ]);
            setStreamingText("");
            setQuestionNumber(doneData.question_number);
            if (doneData.interview_complete) {
              setInterviewComplete(true);
            }
          }
        );
      } catch (e) {
        const errMsg =
          e instanceof Error ? e.message : "Interview interrupted.";
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: `Error: ${errMsg}` },
        ]);
        setStreamingText("");
      } finally {
        setStreaming(false);
      }
    },
    [sessionId, streaming]
  );

  const startInterview = () => {
    setStep(3);
    sendInterviewMessage("");
  };

  const handleInterviewSubmit = () => {
    if (!userInput.trim() || streaming) return;
    sendInterviewMessage(userInput.trim());
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && e.ctrlKey) {
      e.preventDefault();
      handleInterviewSubmit();
    }
  };

  // --- Voice input (Web Speech API) ---

  const toggleRecording = useCallback(() => {
    // Stop recording
    if (isRecording && recognitionRef.current) {
      recognitionRef.current.stop();
      return;
    }

    const SpeechRecognition =
      window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) return;

    const recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.lang = "en-US";
    recognitionRef.current = recognition;

    recognition.onresult = (event: SpeechRecognitionEvent) => {
      let finalTranscript = "";
      let interimTranscript = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i];
        if (result.isFinal) {
          finalTranscript += result[0].transcript;
        } else {
          interimTranscript += result[0].transcript;
        }
      }
      if (finalTranscript) {
        setUserInput((prev) => {
          // Append final transcript to whatever was already in the box
          const separator = prev.length > 0 && !prev.endsWith(" ") ? " " : "";
          return prev + separator + finalTranscript;
        });
      } else if (interimTranscript) {
        // Show interim in a non-destructive way: we append to the current
        // stable text. The final result will replace interim automatically.
        setUserInput((prev) => {
          // Strip any prior interim text (marked by trailing interim block)
          const base = prev.replace(/\u200B.*$/, "");
          const separator =
            base.length > 0 && !base.endsWith(" ") ? " " : "";
          return base + separator + "\u200B" + interimTranscript;
        });
      }
    };

    recognition.onerror = () => {
      setIsRecording(false);
      recognitionRef.current = null;
    };

    recognition.onend = () => {
      setIsRecording(false);
      recognitionRef.current = null;
      // Clean up any remaining zero-width space markers from interim text
      setUserInput((prev) => prev.replace(/\u200B/g, ""));
    };

    recognition.start();
    setIsRecording(true);
  }, [isRecording]);

  // Cleanup recognition on unmount
  useEffect(() => {
    return () => {
      if (recognitionRef.current) {
        recognitionRef.current.abort();
        recognitionRef.current = null;
      }
    };
  }, []);

  // --- Step 4: Finalize ---

  const handleFinalize = async () => {
    setCompiling(true);
    setCompileError("");
    try {
      const data = await apiFetch<ProfileResult>(
        "/api/voice-discovery/finalize",
        {
          method: "POST",
          body: JSON.stringify({
            session_id: sessionId,
            profile_name: profileName,
          }),
        }
      );
      setProfile(data);
      setStep(5);
    } catch (e) {
      setCompileError(
        e instanceof Error
          ? e.message
          : "Profile compilation failed — please try again."
      );
    } finally {
      setCompiling(false);
    }
  };

  // --- Render ---

  return (
    <div className="max-w-3xl mx-auto">
      {/* Progress indicator */}
      <div className="flex items-center gap-2 mb-8">
        {[1, 2, 3, 4, 5].map((s) => (
          <div
            key={s}
            className={`h-1 flex-1 rounded-full transition-colors ${
              s <= step ? "bg-zinc-100" : "bg-zinc-800"
            }`}
          />
        ))}
      </div>

      {/* Step 1: Sample Submission */}
      {step === 1 && (
        <div className="animate-in fade-in">
          <h1 className="text-3xl font-bold mb-2">Voice Discovery</h1>
          <p className="text-zinc-400 mb-6">
            Paste a sample of your writing so we can begin mapping your literary
            DNA.
          </p>

          <textarea
            value={writingSample}
            onChange={(e) => setWritingSample(e.target.value)}
            placeholder="Paste 500+ words of your writing..."
            className="w-full h-64 bg-zinc-900 rounded-lg p-4 text-zinc-100 placeholder:text-zinc-600 resize-none focus:outline-none focus:ring-1 focus:ring-zinc-700"
          />
          <div className="flex justify-between items-center mt-2 mb-4">
            <span
              className={`text-sm ${
                wordCount >= 500 ? "text-zinc-400" : "text-zinc-600"
              }`}
            >
              {wordCount} / 500 minimum
            </span>
            {wordCount > 10000 && (
              <span className="text-sm text-red-400">
                Max 10,000 words
              </span>
            )}
          </div>

          <textarea
            value={sampleContext}
            onChange={(e) => setSampleContext(e.target.value)}
            placeholder="What is this from? (optional)"
            className="w-full h-16 bg-zinc-900 rounded-lg p-4 text-zinc-100 placeholder:text-zinc-600 resize-none focus:outline-none focus:ring-1 focus:ring-zinc-700 mb-6"
          />

          {analyzeError && (
            <p className="text-red-400 text-sm mb-4">{analyzeError}</p>
          )}

          <button
            onClick={handleAnalyze}
            disabled={wordCount < 500 || wordCount > 10000 || analyzing}
            className="w-full rounded-lg bg-zinc-100 px-6 py-3 text-zinc-900 font-medium hover:bg-zinc-200 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {analyzing ? "Reading your work..." : "Analyze My Writing"}
          </button>
        </div>
      )}

      {/* Step 2: Results + Interview Start */}
      {step === 2 && styleMarkers && (
        <div className="animate-in fade-in">
          <h1 className="text-3xl font-bold mb-2">Your Style Markers</h1>
          <p className="text-zinc-400 mb-6">
            Here&apos;s what we found in your writing.
          </p>

          <div className="grid gap-3 mb-8">
            <StyleCard label="Vocabulary" value={styleMarkers.vocabulary_tier} />
            <StyleCard
              label="Rhythm"
              value={`${styleMarkers.avg_sentence_length}. ${styleMarkers.sentence_variety}`}
            />
            <StyleCard label="Pacing" value={styleMarkers.pacing_style} />
            <StyleCard
              label="Emotional Register"
              value={styleMarkers.emotional_register}
            />
            <StyleCard
              label="Sensory World"
              value={styleMarkers.sensory_preference}
            />
            <StyleCard label="Dialogue" value={styleMarkers.dialogue_style} />
            <StyleCard label="Point of View" value={styleMarkers.pov_tendency} />
            <StyleCard label="Tense" value={styleMarkers.tense_preference} />
            <StyleCard label="Humor & Wit" value={styleMarkers.humor_and_wit} />
            <StyleCard
              label="Figurative Language"
              value={styleMarkers.figurative_language}
            />
            <StyleCard
              label="Structural Patterns"
              value={styleMarkers.structural_patterns}
            />

            {styleMarkers.notable_patterns.length > 0 && (
              <div className="bg-zinc-900 rounded-lg p-4">
                <span className="text-sm text-zinc-500 block mb-2">
                  Notable Patterns
                </span>
                <ul className="space-y-1">
                  {styleMarkers.notable_patterns.map((p, i) => (
                    <li key={i} className="text-zinc-200 text-sm">
                      {p}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {styleMarkers.comparable_authors.length > 0 && (
              <div className="bg-zinc-900 rounded-lg p-4">
                <span className="text-sm text-zinc-500 block mb-2">
                  Comparable Voices
                </span>
                <ul className="space-y-1">
                  {styleMarkers.comparable_authors.map((a, i) => (
                    <li key={i} className="text-zinc-200 text-sm">
                      {a}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {styleMarkers.confidence_note && (
              <div className="bg-zinc-900 rounded-lg p-4">
                <span className="text-sm text-zinc-500 block mb-2">
                  Confidence Note
                </span>
                <p className="text-zinc-200 text-sm">
                  {styleMarkers.confidence_note}
                </p>
              </div>
            )}
          </div>

          {/* Conversation Import (optional enrichment step) */}
          {!conversationImportDone && (
            <ConversationImport
              sessionId={sessionId}
              onComplete={() => setConversationImportDone(true)}
              onSkip={() => setConversationImportDone(true)}
            />
          )}

          {/* Interview start — shown after import is done or skipped */}
          {conversationImportDone && (
            <>
              <p className="text-zinc-400 mb-4 mt-8">
                Ready to go deeper? The interview takes about 10 minutes.
              </p>
              <button
                onClick={startInterview}
                className="w-full rounded-lg bg-zinc-100 px-6 py-3 text-zinc-900 font-medium hover:bg-zinc-200 transition-colors"
              >
                Start Interview
              </button>
            </>
          )}
        </div>
      )}

      {/* Step 3: The Interview */}
      {step === 3 && (
        <div className="animate-in fade-in flex flex-col h-[calc(100vh-12rem)]">
          <div className="flex items-center justify-between mb-4">
            <h1 className="text-xl font-bold">Voice Interview</h1>
            <span className="text-sm text-zinc-500">
              {questionNumber > 0
                ? `Question ${questionNumber} of ~8`
                : "Starting..."}
            </span>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto space-y-6 mb-4 pr-2">
            {messages.map((msg, i) => (
              <div key={i}>
                {msg.role === "assistant" ? (
                  <p className="text-zinc-200 leading-relaxed">{msg.content}</p>
                ) : (
                  <div className="bg-zinc-900 rounded-lg p-4">
                    <p className="text-zinc-300">{msg.content}</p>
                  </div>
                )}
              </div>
            ))}

            {streamingText && (
              <p className="text-zinc-200 leading-relaxed">{streamingText}</p>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* Input */}
          {interviewComplete ? (
            <button
              onClick={() => setStep(4)}
              className="w-full rounded-lg bg-zinc-100 px-6 py-3 text-zinc-900 font-medium hover:bg-zinc-200 transition-colors"
            >
              Continue to Profile
            </button>
          ) : (
            <div>
              <div className="relative">
                <textarea
                  value={userInput}
                  onChange={(e) => setUserInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder={
                    isRecording
                      ? "Listening... speak your answer"
                      : "Type your answer..."
                  }
                  disabled={streaming}
                  className="w-full h-24 bg-zinc-900 rounded-lg p-4 pr-12 text-zinc-100 placeholder:text-zinc-600 resize-none focus:outline-none focus:ring-1 focus:ring-zinc-700 disabled:opacity-50"
                />
                {/* Mic button — positioned inside the textarea area */}
                {speechSupported && !streaming && (
                  <button
                    type="button"
                    onClick={toggleRecording}
                    title={isRecording ? "Stop recording" : "Speak your answer"}
                    className={`absolute right-3 top-3 w-8 h-8 flex items-center justify-center rounded-full transition-colors ${
                      isRecording
                        ? "bg-red-500/20 text-red-400 animate-pulse"
                        : "text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800"
                    }`}
                  >
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth={2}
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      className="w-4 h-4"
                    >
                      <rect x="9" y="2" width="6" height="11" rx="3" />
                      <path d="M19 10v1a7 7 0 0 1-14 0v-1" />
                      <line x1="12" y1="19" x2="12" y2="22" />
                    </svg>
                  </button>
                )}
              </div>
              <div className="flex justify-between items-center mt-2">
                <span className="text-xs text-zinc-600">
                  {isRecording ? (
                    <span className="text-red-400">Recording...</span>
                  ) : (
                    "Ctrl+Enter to send"
                  )}
                </span>
                <button
                  onClick={handleInterviewSubmit}
                  disabled={!userInput.trim() || streaming}
                  className="rounded-lg bg-zinc-100 px-5 py-2 text-sm text-zinc-900 font-medium hover:bg-zinc-200 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {streaming ? "Listening..." : "Send"}
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Step 4: Profile Generation */}
      {step === 4 && (
        <div className="animate-in fade-in">
          <h1 className="text-3xl font-bold mb-2">Name Your Voice Profile</h1>
          <p className="text-zinc-400 mb-6">
            Give this voice profile a name you&apos;ll recognize.
          </p>

          <input
            type="text"
            value={profileName}
            onChange={(e) => setProfileName(e.target.value)}
            maxLength={100}
            className="w-full bg-zinc-900 rounded-lg p-4 text-zinc-100 placeholder:text-zinc-600 focus:outline-none focus:ring-1 focus:ring-zinc-700 mb-6"
          />

          {compileError && (
            <p className="text-red-400 text-sm mb-4">{compileError}</p>
          )}

          <button
            onClick={handleFinalize}
            disabled={!profileName.trim() || compiling}
            className="w-full rounded-lg bg-zinc-100 px-6 py-3 text-zinc-900 font-medium hover:bg-zinc-200 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {compiling
              ? "Compiling your literary DNA..."
              : "Build My Voice DNA"}
          </button>
        </div>
      )}

      {/* Step 5: Profile Display */}
      {step === 5 && profile && (
        <div className="animate-in fade-in">
          <h1 className="text-3xl font-bold mb-2">{profile.profile_name}</h1>
          <p className="text-lg text-zinc-300 mb-8 leading-relaxed">
            {profile.voice_summary}
          </p>

          {/* Literary DNA */}
          <h2 className="text-xl font-semibold mb-3">Literary DNA</h2>
          <div className="grid gap-3 mb-8">
            <StyleCard
              label="Vocabulary"
              value={profile.literary_dna.vocabulary_tier}
            />
            <StyleCard
              label="Sentence Rhythm"
              value={profile.literary_dna.sentence_rhythm}
            />
            <StyleCard
              label="Pacing"
              value={profile.literary_dna.pacing_style}
            />
            <StyleCard
              label="Emotional Register"
              value={profile.literary_dna.emotional_register}
            />
            <StyleCard
              label="Sensory Mode"
              value={profile.literary_dna.sensory_mode}
            />
            <StyleCard
              label="Dialogue"
              value={profile.literary_dna.dialogue_approach}
            />
            <StyleCard
              label="Point of View"
              value={profile.literary_dna.pov_preference}
            />
            <StyleCard
              label="Tense"
              value={profile.literary_dna.tense_preference}
            />
            <StyleCard
              label="Humor"
              value={profile.literary_dna.humor_style}
            />
            <StyleCard
              label="Darkness"
              value={profile.literary_dna.darkness_calibration}
            />

            {/* Cognitive Style */}
            <div className="bg-zinc-900 rounded-lg p-4">
              <span className="text-sm text-zinc-500 block mb-2">
                Cognitive Style
              </span>
              <div className="grid grid-cols-2 gap-2 text-sm">
                <div>
                  <span className="text-zinc-500">Processing: </span>
                  <span className="text-zinc-200">
                    {profile.literary_dna.cognitive_style.processing_mode}
                  </span>
                </div>
                <div>
                  <span className="text-zinc-500">Entry Point: </span>
                  <span className="text-zinc-200">
                    {profile.literary_dna.cognitive_style.story_entry_point}
                  </span>
                </div>
                <div>
                  <span className="text-zinc-500">Revision: </span>
                  <span className="text-zinc-200">
                    {profile.literary_dna.cognitive_style.revision_pattern}
                  </span>
                </div>
                <div>
                  <span className="text-zinc-500">Structure: </span>
                  <span className="text-zinc-200">
                    {profile.literary_dna.cognitive_style.plotter_pantser}
                  </span>
                </div>
              </div>
            </div>

            {profile.literary_dna.notable_patterns.length > 0 && (
              <div className="bg-zinc-900 rounded-lg p-4">
                <span className="text-sm text-zinc-500 block mb-2">
                  Notable Patterns
                </span>
                <ul className="space-y-1">
                  {profile.literary_dna.notable_patterns.map((p, i) => (
                    <li key={i} className="text-zinc-200 text-sm">
                      {p}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {profile.literary_dna.comparable_authors.length > 0 && (
              <div className="bg-zinc-900 rounded-lg p-4">
                <span className="text-sm text-zinc-500 block mb-2">
                  Comparable Authors
                </span>
                <ul className="space-y-1">
                  {profile.literary_dna.comparable_authors.map((a, i) => (
                    <li key={i} className="text-zinc-200 text-sm">
                      {a}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          {/* Influences */}
          <h2 className="text-xl font-semibold mb-3">Influences</h2>
          <div className="grid gap-3 mb-8">
            <TagCard label="Rhythm From" items={profile.influences.rhythm_from} />
            <TagCard
              label="Structure From"
              items={profile.influences.structure_from}
            />
            <TagCard label="Tone From" items={profile.influences.tone_from} />
            <TagCard
              label="Anti-Influences"
              items={profile.influences.anti_influences}
            />
          </div>

          {/* Anti-Slop */}
          <h2 className="text-xl font-semibold mb-3">Anti-Slop Rules</h2>
          <div className="grid gap-3 mb-8">
            <TagCard
              label="Banned Words"
              items={profile.anti_slop.personal_banned_words}
            />
            <TagCard
              label="Banned Patterns"
              items={profile.anti_slop.personal_banned_patterns}
            />
            <TagCard
              label="Cringe Triggers"
              items={profile.anti_slop.cringe_triggers}
            />
            <TagCard
              label="Genre Constraints"
              items={profile.anti_slop.genre_constraints}
            />
          </div>

          {/* Voice Instruction (expandable) */}
          <div className="mb-8">
            <button
              onClick={() => setShowVoiceInstruction(!showVoiceInstruction)}
              className="text-zinc-400 text-sm hover:text-zinc-200 transition-colors"
            >
              {showVoiceInstruction ? "Hide" : "Show"} compiled voice
              instruction
            </button>
            {showVoiceInstruction && (
              <div className="mt-3 bg-zinc-900 rounded-lg p-4">
                <p className="text-zinc-300 text-sm whitespace-pre-wrap leading-relaxed">
                  {profile.voice_instruction}
                </p>
              </div>
            )}
          </div>

          {/* CTA */}
          <button
            onClick={() => router.push("/dashboard")}
            className="w-full rounded-lg bg-zinc-100 px-6 py-3 text-zinc-900 font-medium hover:bg-zinc-200 transition-colors"
          >
            Start Writing
          </button>
        </div>
      )}
    </div>
  );
}

// --- Sub-components ---

function StyleCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-zinc-900 rounded-lg p-4">
      <span className="text-sm text-zinc-500 block mb-1">{label}</span>
      <p className="text-zinc-200 text-sm">{value}</p>
    </div>
  );
}

function TagCard({ label, items }: { label: string; items: string[] }) {
  if (!items || items.length === 0) return null;
  return (
    <div className="bg-zinc-900 rounded-lg p-4">
      <span className="text-sm text-zinc-500 block mb-2">{label}</span>
      <ul className="space-y-1">
        {items.map((item, i) => (
          <li key={i} className="text-zinc-200 text-sm">
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
}
