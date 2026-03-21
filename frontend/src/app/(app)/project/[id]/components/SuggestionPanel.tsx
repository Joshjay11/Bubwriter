"use client";

import { useState } from "react";
import type {
  ExtractionSuggestions,
  CharacterSuggestion,
  LocationSuggestion,
  CharacterUpdate,
  WorldRuleSuggestion,
  PlotBeatSuggestion,
  KnowledgeEvent,
  TimelineEvent,
  StateChange,
  ContradictionWarning,
} from "@/lib/api";
import { addBibleEntry } from "@/lib/api";

interface SuggestionPanelProps {
  projectId: string;
  suggestions: ExtractionSuggestions;
  onClose: () => void;
}

export function SuggestionPanel({
  projectId,
  suggestions,
  onClose,
}: SuggestionPanelProps) {
  const [dismissed, setDismissed] = useState<Set<string>>(new Set());
  const [approved, setApproved] = useState<Set<string>>(new Set());

  const dismiss = (key: string) => {
    setDismissed((prev) => new Set(prev).add(key));
  };

  const approve = async (key: string, section: string, entry: Record<string, unknown>) => {
    try {
      await addBibleEntry(projectId, section, entry);
      setApproved((prev) => new Set(prev).add(key));
    } catch {
      // silent — card stays visible so user can retry
    }
  };

  const isVisible = (key: string) => !dismissed.has(key) && !approved.has(key);

  const totalVisible =
    suggestions.new_characters.filter((_, i) => isVisible(`char_${i}`)).length +
    suggestions.new_locations.filter((_, i) => isVisible(`loc_${i}`)).length +
    suggestions.character_updates.filter((_, i) => isVisible(`update_${i}`)).length +
    suggestions.new_world_rules.filter((_, i) => isVisible(`rule_${i}`)).length +
    suggestions.plot_beats.filter((_, i) => isVisible(`beat_${i}`)).length +
    (suggestions.knowledge_events ?? []).filter((_, i) => isVisible(`know_${i}`)).length +
    (suggestions.timeline_events ?? []).filter((_, i) => isVisible(`time_${i}`)).length +
    (suggestions.state_changes ?? []).filter((_, i) => isVisible(`state_${i}`)).length +
    (suggestions.contradiction_warnings ?? []).filter((_, i) => isVisible(`contra_${i}`)).length;

  if (totalVisible === 0) return null;

  return (
    <div className="border-t border-zinc-800 bg-zinc-900/80 max-h-64 overflow-y-auto">
      <div className="flex items-center justify-between px-4 py-2 border-b border-zinc-800">
        <span className="text-xs font-medium text-zinc-400 uppercase tracking-wide">
          Story Bible Suggestions
        </span>
        <button
          onClick={onClose}
          className="text-xs text-zinc-500 hover:text-zinc-300"
        >
          Dismiss all
        </button>
      </div>

      <div className="p-3 flex flex-wrap gap-2">
        {suggestions.new_characters.map((c, i) => {
          const key = `char_${i}`;
          if (!isVisible(key)) return null;
          return (
            <CharacterCard
              key={key}
              suggestion={c}
              onApprove={() =>
                approve(key, "characters", {
                  id: `char_${Date.now()}_${i}`,
                  name: c.name,
                  description: c.description,
                  role: c.role,
                  first_appearance: c.first_appearance,
                  knowledge: [],
                  relationships: [],
                  source: "auto",
                })
              }
              onDismiss={() => dismiss(key)}
            />
          );
        })}

        {suggestions.new_locations.map((l, i) => {
          const key = `loc_${i}`;
          if (!isVisible(key)) return null;
          return (
            <LocationCard
              key={key}
              suggestion={l}
              onApprove={() =>
                approve(key, "locations", {
                  id: `loc_${Date.now()}_${i}`,
                  name: l.name,
                  description: l.description,
                  sensory_details: l.sensory_details,
                  first_appearance: l.first_appearance,
                  source: "auto",
                })
              }
              onDismiss={() => dismiss(key)}
            />
          );
        })}

        {suggestions.character_updates.map((u, i) => {
          const key = `update_${i}`;
          if (!isVisible(key)) return null;
          return (
            <UpdateCard
              key={key}
              update={u}
              onApprove={() =>
                approve(key, "character_updates", {
                  character_name: u.character_name,
                  update_type: u.update_type,
                  detail: u.detail,
                  source: "auto",
                })
              }
              onDismiss={() => dismiss(key)}
            />
          );
        })}

        {suggestions.new_world_rules.map((r, i) => {
          const key = `rule_${i}`;
          if (!isVisible(key)) return null;
          return (
            <WorldRuleCard
              key={key}
              rule={r}
              onApprove={() =>
                approve(key, "world_rules", {
                  id: `rule_${Date.now()}_${i}`,
                  category: r.category,
                  rule: r.rule,
                  exceptions: r.exceptions,
                  implications: r.implications,
                  source: "auto",
                })
              }
              onDismiss={() => dismiss(key)}
            />
          );
        })}

        {suggestions.plot_beats.map((b, i) => {
          const key = `beat_${i}`;
          if (!isVisible(key)) return null;
          return (
            <PlotBeatCard
              key={key}
              beat={b}
              onApprove={() =>
                approve(key, "plot_beats", {
                  id: `beat_${Date.now()}_${i}`,
                  beat: b.beat,
                  characters_involved: b.characters_involved,
                  consequences: b.consequences,
                  source: "auto",
                })
              }
              onDismiss={() => dismiss(key)}
            />
          );
        })}

        {(suggestions.knowledge_events ?? []).map((k, i) => {
          const key = `know_${i}`;
          if (!isVisible(key)) return null;
          return (
            <KnowledgeEventCard
              key={key}
              event={k}
              onApprove={() => {
                if (k.type === "secret_established") {
                  approve(key, "story_secrets", {
                    id: `secret_${Date.now()}_${i}`,
                    summary: k.summary,
                    characters_who_know: k.witnesses,
                    characters_who_dont_know: k.non_witnesses,
                    reveal_status: "restricted",
                    source: "auto",
                  });
                } else if (k.type === "knowledge_gained") {
                  approve(key, "character_updates", {
                    character_name: k.character_names[0] ?? "unknown",
                    update_type: "new_knowledge",
                    detail: k.summary,
                    method: k.method,
                    source: "auto",
                  });
                } else {
                  // pov_leak_warning — just dismiss, it's informational
                  dismiss(key);
                }
              }}
              onDismiss={() => dismiss(key)}
            />
          );
        })}

        {(suggestions.contradiction_warnings ?? []).map((w, i) => {
          const key = `contra_${i}`;
          if (!isVisible(key)) return null;
          return (
            <ContradictionCard
              key={key}
              warning={w}
              onDismiss={() => dismiss(key)}
            />
          );
        })}

        {(suggestions.timeline_events ?? []).map((t, i) => {
          const key = `time_${i}`;
          if (!isVisible(key)) return null;
          return (
            <TimelineCard
              key={key}
              event={t}
              onApprove={() =>
                approve(key, "timeline", {
                  id: `time_${Date.now()}_${i}`,
                  event: t.event,
                  when: t.when,
                  characters_present: t.characters_present,
                  source: "auto",
                })
              }
              onDismiss={() => dismiss(key)}
            />
          );
        })}

        {(suggestions.state_changes ?? []).map((s, i) => {
          const key = `state_${i}`;
          if (!isVisible(key)) return null;
          const section =
            s.entity_type === "character"
              ? "character_states"
              : "object_states";
          return (
            <StateChangeCard
              key={key}
              change={s}
              onApprove={() =>
                approve(key, section, {
                  ...(s.entity_type === "character"
                    ? {
                        character_id: s.entity_name,
                        state_type: s.state_type,
                        description: s.description,
                        status: "active",
                      }
                    : {
                        object_name: s.entity_name,
                        current_state: s.description,
                      }),
                  source: "auto",
                })
              }
              onDismiss={() => dismiss(key)}
            />
          );
        })}
      </div>
    </div>
  );
}

// --- Card Components ---

function CardShell({
  label,
  color,
  children,
  onApprove,
  onDismiss,
}: {
  label: string;
  color: string;
  children: React.ReactNode;
  onApprove: () => void;
  onDismiss: () => void;
}) {
  return (
    <div className="bg-zinc-800/60 rounded-lg p-3 text-sm max-w-xs border border-zinc-700/50">
      <span
        className={`inline-block text-[10px] font-semibold uppercase tracking-wider mb-1 ${color}`}
      >
        {label}
      </span>
      <div className="text-zinc-300 mb-2">{children}</div>
      <div className="flex gap-2">
        <button
          onClick={onApprove}
          className="text-xs px-2 py-1 rounded bg-emerald-600/20 text-emerald-400 hover:bg-emerald-600/30"
        >
          Add to Bible
        </button>
        <button
          onClick={onDismiss}
          className="text-xs px-2 py-1 rounded bg-zinc-700/40 text-zinc-500 hover:text-zinc-300"
        >
          Dismiss
        </button>
      </div>
    </div>
  );
}

function CharacterCard({
  suggestion,
  onApprove,
  onDismiss,
}: {
  suggestion: CharacterSuggestion;
  onApprove: () => void;
  onDismiss: () => void;
}) {
  return (
    <CardShell label="Character" color="text-blue-400" onApprove={onApprove} onDismiss={onDismiss}>
      <p className="font-medium text-zinc-200">{suggestion.name}</p>
      {suggestion.description && (
        <p className="text-zinc-400 text-xs mt-0.5">{suggestion.description}</p>
      )}
      <p className="text-zinc-500 text-xs mt-0.5">Role: {suggestion.role}</p>
    </CardShell>
  );
}

function LocationCard({
  suggestion,
  onApprove,
  onDismiss,
}: {
  suggestion: LocationSuggestion;
  onApprove: () => void;
  onDismiss: () => void;
}) {
  return (
    <CardShell label="Location" color="text-amber-400" onApprove={onApprove} onDismiss={onDismiss}>
      <p className="font-medium text-zinc-200">{suggestion.name}</p>
      {suggestion.description && (
        <p className="text-zinc-400 text-xs mt-0.5">{suggestion.description}</p>
      )}
    </CardShell>
  );
}

function UpdateCard({
  update,
  onApprove,
  onDismiss,
}: {
  update: CharacterUpdate;
  onApprove: () => void;
  onDismiss: () => void;
}) {
  return (
    <CardShell label="Character Update" color="text-purple-400" onApprove={onApprove} onDismiss={onDismiss}>
      <p className="font-medium text-zinc-200">{update.character_name}</p>
      <p className="text-zinc-400 text-xs mt-0.5">
        {update.update_type.replace("_", " ")}: {update.detail}
      </p>
    </CardShell>
  );
}

function WorldRuleCard({
  rule,
  onApprove,
  onDismiss,
}: {
  rule: WorldRuleSuggestion;
  onApprove: () => void;
  onDismiss: () => void;
}) {
  return (
    <CardShell label="World Rule" color="text-teal-400" onApprove={onApprove} onDismiss={onDismiss}>
      <p className="font-medium text-zinc-200">{rule.rule}</p>
      <p className="text-zinc-500 text-xs mt-0.5">Category: {rule.category}</p>
    </CardShell>
  );
}

function PlotBeatCard({
  beat,
  onApprove,
  onDismiss,
}: {
  beat: PlotBeatSuggestion;
  onApprove: () => void;
  onDismiss: () => void;
}) {
  return (
    <CardShell label="Plot Beat" color="text-rose-400" onApprove={onApprove} onDismiss={onDismiss}>
      <p className="text-zinc-300">{beat.beat}</p>
      {beat.characters_involved.length > 0 && (
        <p className="text-zinc-500 text-xs mt-0.5">
          Characters: {beat.characters_involved.join(", ")}
        </p>
      )}
    </CardShell>
  );
}

function KnowledgeEventCard({
  event,
  onApprove,
  onDismiss,
}: {
  event: KnowledgeEvent;
  onApprove: () => void;
  onDismiss: () => void;
}) {
  if (event.type === "pov_leak_warning") {
    return (
      <div className="bg-amber-950/40 rounded-lg p-3 text-sm max-w-xs border border-amber-700/50">
        <span className="inline-block text-[10px] font-semibold uppercase tracking-wider mb-1 text-amber-400">
          POV Leak Warning
        </span>
        <div className="text-zinc-300 mb-2">
          <p className="font-medium text-amber-300">{event.issue ?? event.summary}</p>
          {event.character_names.length > 0 && (
            <p className="text-zinc-400 text-xs mt-0.5">
              Character: {event.character_names.join(", ")}
            </p>
          )}
        </div>
        <div className="flex gap-2">
          <button
            onClick={onDismiss}
            className="text-xs px-2 py-1 rounded bg-zinc-700/40 text-zinc-400 hover:text-zinc-300"
          >
            Intentional — dismiss
          </button>
        </div>
      </div>
    );
  }

  const label = event.type === "secret_established" ? "Secret" : "Knowledge Gained";
  const color = event.type === "secret_established" ? "text-orange-400" : "text-cyan-400";
  const approveLabel = event.type === "secret_established" ? "Track Secret" : "Add to Bible";

  return (
    <div className="bg-zinc-800/60 rounded-lg p-3 text-sm max-w-xs border border-zinc-700/50">
      <span
        className={`inline-block text-[10px] font-semibold uppercase tracking-wider mb-1 ${color}`}
      >
        {label}
      </span>
      <div className="text-zinc-300 mb-2">
        <p>{event.summary}</p>
        {event.witnesses.length > 0 && (
          <p className="text-zinc-500 text-xs mt-0.5">
            Witnesses: {event.witnesses.join(", ")}
          </p>
        )}
        {event.non_witnesses.length > 0 && (
          <p className="text-zinc-500 text-xs mt-0.5">
            Unaware: {event.non_witnesses.join(", ")}
          </p>
        )}
        {event.method && (
          <p className="text-zinc-500 text-xs mt-0.5">Method: {event.method}</p>
        )}
      </div>
      <div className="flex gap-2">
        <button
          onClick={onApprove}
          className="text-xs px-2 py-1 rounded bg-emerald-600/20 text-emerald-400 hover:bg-emerald-600/30"
        >
          {approveLabel}
        </button>
        <button
          onClick={onDismiss}
          className="text-xs px-2 py-1 rounded bg-zinc-700/40 text-zinc-500 hover:text-zinc-300"
        >
          Dismiss
        </button>
      </div>
    </div>
  );
}

function ContradictionCard({
  warning,
  onDismiss,
}: {
  warning: ContradictionWarning;
  onDismiss: () => void;
}) {
  return (
    <div className="bg-red-950/40 rounded-lg p-3 text-sm max-w-xs border border-red-700/50">
      <span className="inline-block text-[10px] font-semibold uppercase tracking-wider mb-1 text-red-400">
        Contradiction
      </span>
      <div className="text-zinc-300 mb-2">
        <p className="font-medium text-red-300">{warning.issue}</p>
        {warning.conflicting_fact && (
          <p className="text-zinc-400 text-xs mt-0.5">
            Conflicts with: {warning.conflicting_fact}
          </p>
        )}
      </div>
      <div className="flex gap-2">
        <button
          onClick={onDismiss}
          className="text-xs px-2 py-1 rounded bg-zinc-700/40 text-zinc-400 hover:text-zinc-300"
        >
          Intentional — dismiss
        </button>
      </div>
    </div>
  );
}

function TimelineCard({
  event,
  onApprove,
  onDismiss,
}: {
  event: TimelineEvent;
  onApprove: () => void;
  onDismiss: () => void;
}) {
  return (
    <CardShell label="Timeline" color="text-sky-400" onApprove={onApprove} onDismiss={onDismiss}>
      <p className="text-zinc-300">{event.event}</p>
      {event.when && (
        <p className="text-zinc-500 text-xs mt-0.5">When: {event.when}</p>
      )}
      {event.characters_present.length > 0 && (
        <p className="text-zinc-500 text-xs mt-0.5">
          Present: {event.characters_present.join(", ")}
        </p>
      )}
    </CardShell>
  );
}

function StateChangeCard({
  change,
  onApprove,
  onDismiss,
}: {
  change: StateChange;
  onApprove: () => void;
  onDismiss: () => void;
}) {
  const label =
    change.entity_type === "character"
      ? "Character State"
      : change.entity_type === "object"
        ? "Object State"
        : "Location State";
  const color =
    change.entity_type === "character"
      ? "text-pink-400"
      : change.entity_type === "object"
        ? "text-yellow-400"
        : "text-lime-400";

  return (
    <CardShell label={label} color={color} onApprove={onApprove} onDismiss={onDismiss}>
      <p className="font-medium text-zinc-200">{change.entity_name}</p>
      <p className="text-zinc-400 text-xs mt-0.5">
        {change.state_type}: {change.description}
      </p>
      {change.previous_state && (
        <p className="text-zinc-500 text-xs mt-0.5">
          Was: {change.previous_state}
        </p>
      )}
    </CardShell>
  );
}
