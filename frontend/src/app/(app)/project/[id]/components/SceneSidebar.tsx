"use client";

import { useState, useCallback } from "react";
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import type { SceneListItem } from "@/lib/api";

interface SceneSidebarProps {
  scenes: SceneListItem[];
  activeSceneId: string | null;
  onSceneSelect: (sceneId: string) => void;
  onSceneDelete: (sceneId: string) => void;
  onScenePin: (sceneId: string, pinned: boolean) => void;
  onSceneRename: (sceneId: string, label: string) => void;
  onScenesReorder: (orderedIds: string[]) => void;
  onNewScene: () => void;
  isGenerating: boolean;
}

export function SceneSidebar({
  scenes,
  activeSceneId,
  onSceneSelect,
  onSceneDelete,
  onScenePin,
  onSceneRename,
  onScenesReorder,
  onNewScene,
  isGenerating,
}: SceneSidebarProps) {
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);

  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: { distance: 5 },
    }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    })
  );

  const handleDragEnd = useCallback(
    (event: DragEndEvent) => {
      const { active, over } = event;
      if (!over || active.id === over.id) return;

      const oldIndex = scenes.findIndex((s) => s.id === active.id);
      const newIndex = scenes.findIndex((s) => s.id === over.id);
      if (oldIndex === -1 || newIndex === -1) return;

      const reordered = arrayMove(scenes, oldIndex, newIndex);
      onScenesReorder(reordered.map((s) => s.id));
    },
    [scenes, onScenesReorder]
  );

  return (
    <div className="w-56 border-r border-zinc-800 flex flex-col bg-zinc-950 flex-shrink-0">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800">
        <h3 className="text-xs font-semibold text-zinc-500 uppercase tracking-wider">
          Scenes
        </h3>
        <button
          onClick={onNewScene}
          disabled={isGenerating}
          className="text-zinc-500 hover:text-zinc-300 transition-colors text-lg leading-none disabled:opacity-40"
          title="New scene"
        >
          +
        </button>
      </div>

      {/* Scene list */}
      <div className="flex-1 overflow-y-auto">
        {scenes.length === 0 ? (
          <div className="px-4 py-8 text-center">
            <p className="text-zinc-600 text-xs">No scenes yet</p>
          </div>
        ) : (
          <DndContext
            sensors={sensors}
            collisionDetection={closestCenter}
            onDragEnd={handleDragEnd}
          >
            <SortableContext
              items={scenes.map((s) => s.id)}
              strategy={verticalListSortingStrategy}
            >
              {scenes.map((scene) => (
                <SortableSceneCard
                  key={scene.id}
                  scene={scene}
                  isActive={scene.id === activeSceneId}
                  onSelect={() => onSceneSelect(scene.id)}
                  onPin={() => onScenePin(scene.id, !scene.is_pinned)}
                  onRename={(label) => onSceneRename(scene.id, label)}
                  onDelete={() => {
                    if (deleteConfirmId === scene.id) {
                      onSceneDelete(scene.id);
                      setDeleteConfirmId(null);
                    } else {
                      setDeleteConfirmId(scene.id);
                    }
                  }}
                  showDeleteConfirm={deleteConfirmId === scene.id}
                  onCancelDelete={() => setDeleteConfirmId(null)}
                />
              ))}
            </SortableContext>
          </DndContext>
        )}
      </div>
    </div>
  );
}

// --- Sortable Scene Card ---

function SortableSceneCard({
  scene,
  isActive,
  onSelect,
  onPin,
  onRename,
  onDelete,
  showDeleteConfirm,
  onCancelDelete,
}: {
  scene: SceneListItem;
  isActive: boolean;
  onSelect: () => void;
  onPin: () => void;
  onRename: (label: string) => void;
  onDelete: () => void;
  showDeleteConfirm: boolean;
  onCancelDelete: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [editLabel, setEditLabel] = useState(
    scene.scene_label || ""
  );
  const [showMenu, setShowMenu] = useState(false);

  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: scene.id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  const displayLabel =
    scene.scene_label ||
    (scene.user_prompt.length > 40
      ? scene.user_prompt.slice(0, 37) + "..."
      : scene.user_prompt);

  const handleSaveLabel = () => {
    const trimmed = editLabel.trim();
    if (trimmed) {
      onRename(trimmed);
    }
    setEditing(false);
  };

  if (showDeleteConfirm) {
    return (
      <div
        ref={setNodeRef}
        style={style}
        className="px-3 py-2 border-b border-zinc-800 bg-red-950/30"
      >
        <p className="text-xs text-red-400 mb-2">Delete this scene?</p>
        <div className="flex gap-2">
          <button
            onClick={onDelete}
            className="text-xs text-red-400 hover:text-red-300"
          >
            Delete
          </button>
          <button
            onClick={onCancelDelete}
            className="text-xs text-zinc-500 hover:text-zinc-300"
          >
            Cancel
          </button>
        </div>
      </div>
    );
  }

  return (
    <div
      ref={setNodeRef}
      style={style}
      {...attributes}
      {...listeners}
      onClick={onSelect}
      onContextMenu={(e) => {
        e.preventDefault();
        setShowMenu(!showMenu);
      }}
      className={`px-3 py-2.5 border-b border-zinc-800 cursor-pointer transition-colors group relative ${
        isActive
          ? "bg-zinc-800/80 border-l-2 border-l-zinc-400"
          : "hover:bg-zinc-900"
      }`}
    >
      {/* Label */}
      {editing ? (
        <input
          type="text"
          value={editLabel}
          onChange={(e) => setEditLabel(e.target.value)}
          onBlur={handleSaveLabel}
          onKeyDown={(e) => {
            if (e.key === "Enter") handleSaveLabel();
            if (e.key === "Escape") setEditing(false);
          }}
          onClick={(e) => e.stopPropagation()}
          autoFocus
          className="w-full bg-zinc-800 rounded px-1.5 py-0.5 text-xs text-zinc-200 focus:outline-none focus:ring-1 focus:ring-zinc-600"
        />
      ) : (
        <div className="flex items-center gap-1.5">
          {scene.is_pinned && (
            <span className="text-zinc-500 text-[10px]" title="Pinned">
              &#x1F4CC;
            </span>
          )}
          <span className="text-xs text-zinc-300 truncate block">
            {displayLabel}
          </span>
        </div>
      )}

      {/* Metadata */}
      <div className="flex items-center gap-2 mt-1">
        {scene.word_count != null && scene.word_count > 0 && (
          <span className="text-[10px] text-zinc-600">
            {scene.word_count.toLocaleString()} w
          </span>
        )}
        {scene.has_polish && (
          <span className="text-[10px] text-zinc-600" title="Polished">
            &#x2728;
          </span>
        )}
      </div>

      {/* Context menu */}
      {showMenu && (
        <div
          className="absolute right-2 top-8 z-20 bg-zinc-800 border border-zinc-700 rounded-md shadow-lg py-1 min-w-[100px]"
          onClick={(e) => e.stopPropagation()}
        >
          <button
            onClick={() => {
              setEditing(true);
              setShowMenu(false);
            }}
            className="w-full text-left px-3 py-1.5 text-xs text-zinc-300 hover:bg-zinc-700"
          >
            Rename
          </button>
          <button
            onClick={() => {
              onPin();
              setShowMenu(false);
            }}
            className="w-full text-left px-3 py-1.5 text-xs text-zinc-300 hover:bg-zinc-700"
          >
            {scene.is_pinned ? "Unpin" : "Pin"}
          </button>
          <button
            onClick={() => {
              onDelete();
              setShowMenu(false);
            }}
            className="w-full text-left px-3 py-1.5 text-xs text-red-400 hover:bg-zinc-700"
          >
            Delete
          </button>
        </div>
      )}

      {/* Hover actions */}
      <div className="absolute right-2 top-2 opacity-0 group-hover:opacity-100 transition-opacity">
        <button
          onClick={(e) => {
            e.stopPropagation();
            setShowMenu(!showMenu);
          }}
          className="text-zinc-600 hover:text-zinc-400 text-xs px-1"
        >
          &bull;&bull;&bull;
        </button>
      </div>
    </div>
  );
}
