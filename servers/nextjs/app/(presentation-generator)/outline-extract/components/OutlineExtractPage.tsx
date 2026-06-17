"use client";

import React, { useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useDispatch, useSelector } from "react-redux";
import { Send } from "lucide-react";

import { RootState } from "@/store/store";
import {
  setOutlines,
} from "@/store/slices/presentationGeneration";
import { Button } from "@/components/ui/button";
import { notify } from "@/components/ui/sonner";
import { PresentationGenerationApi } from "@/app/(presentation-generator)/services/api/presentation-generation";
import OutlineContent from "@/app/(presentation-generator)/outline/components/OutlineContent";

type ChatMessage = { role: "user" | "assistant"; content: string };

const SUGGESTIONS = [
  "슬라이드를 8개로 줄여주세요",
  "3번 슬라이드를 둘로 나눠주세요",
  "각 슬라이드를 더 간결하게 만들어주세요",
];

const OutlineExtractPage: React.FC = () => {
  const router = useRouter();
  const searchParams = useSearchParams();
  const dispatch = useDispatch();

  const presetId = searchParams.get("preset");

  const { presentation_id, outlines } = useSelector(
    (state: RootState) => state.presentationGeneration
  );

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [isBusy, setIsBusy] = useState(false);
  const [hasExtracted, setHasExtracted] = useState(false);
  const [isSavingPreset, setIsSavingPreset] = useState(false);
  const didAutoExtract = useRef(false);

  // Auto-run the first extraction on mount.
  useEffect(() => {
    if (!presentation_id) {
      router.replace("/upload");
      return;
    }
    if (didAutoExtract.current) return;
    didAutoExtract.current = true;
    void runRefine(undefined, true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [presentation_id]);

  const runRefine = async (instruction?: string, applyPreset = false) => {
    if (!presentation_id) return;
    setIsBusy(true);
    try {
      const res = await PresentationGenerationApi.refineOutline({
        presentation_id,
        instruction,
        conversation_id: conversationId,
        // Apply the saved preset only on the first extraction.
        preset_id: applyPreset ? presetId : null,
      });
      setConversationId(res.conversation_id);
      dispatch(setOutlines(res.outlines));
      setHasExtracted(true);
      if (res.summary) {
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: res.summary },
        ]);
      }
    } catch (error: any) {
      notify.error(
        "Outline failed",
        error?.message || "Could not extract or refine the outline."
      );
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content:
            "⚠️ " + (error?.message || "Something went wrong. Try again."),
        },
      ]);
    } finally {
      setIsBusy(false);
    }
  };

  const handleSend = async (text?: string) => {
    const instruction = (text ?? input).trim();
    if (!instruction || isBusy) return;
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: instruction }]);
    await runRefine(instruction);
  };

  const handleSavePreset = async () => {
    if (!presentation_id || !conversationId) {
      notify.error("No conversation", "Refine the outline before saving a preset.");
      return;
    }
    const name = window.prompt(
      "이 교정 규칙을 프리셋 이름으로 저장합니다 (예: 교과서 표준)"
    );
    if (!name || !name.trim()) return;

    setIsSavingPreset(true);
    try {
      const preset = await PresentationGenerationApi.saveOutlinePreset({
        presentation_id,
        conversation_id: conversationId,
        name: name.trim(),
      });
      notify.success(
        "프리셋 저장됨",
        `"${preset.name}" — 다음 단원 업로드 시 적용할 수 있어요.`
      );
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content:
            `💾 프리셋 "${preset.name}" 저장됨. 규칙:\n` + (preset.rules || ""),
        },
      ]);
    } catch (error: any) {
      notify.error("저장 실패", error?.message || "프리셋을 저장하지 못했습니다.");
    } finally {
      setIsSavingPreset(false);
    }
  };

  const handleConfirm = () => {
    if (!outlines || outlines.length === 0) {
      notify.error("No outline", "Extract an outline before continuing.");
      return;
    }
    // Outline is already persisted on the presentation and seeded in the store,
    // so the existing /outline page skips streaming and lets the user pick a
    // template before running the normal generation pipeline.
    router.push("/outline");
  };

  return (
    <div className="max-w-[1440px] mx-auto px-4 py-6">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Left: refinement chat */}
        <div className="flex flex-col h-[calc(100vh-160px)] border border-gray-200 rounded-xl bg-white">
          <div className="px-4 py-3 border-b border-gray-100">
            <h2 className="font-semibold text-gray-900">
              아웃라인 정제 (InDesign)
            </h2>
            <p className="text-xs text-gray-500 mt-0.5">
              업로드한 문서에서 추출된 슬라이드 아웃라인을 대화로 다듬으세요.
            </p>
          </div>

          <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
            {messages.length === 0 && isBusy && (
              <div className="text-sm text-gray-500">
                문서에서 아웃라인을 추출하는 중…
              </div>
            )}
            {messages.map((m, i) => (
              <div
                key={i}
                className={
                  m.role === "user" ? "flex justify-end" : "flex justify-start"
                }
              >
                <div
                  className={
                    "max-w-[85%] rounded-2xl px-4 py-2 text-sm " +
                    (m.role === "user"
                      ? "bg-[#5146E5] text-white"
                      : "bg-gray-100 text-gray-800")
                  }
                >
                  {m.content}
                </div>
              </div>
            ))}
            {isBusy && messages.length > 0 && (
              <div className="text-xs text-gray-400">처리 중…</div>
            )}
          </div>

          {/* Suggestions */}
          <div className="px-4 pb-2 flex flex-wrap gap-2">
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                disabled={isBusy || !hasExtracted}
                onClick={() => handleSend(s)}
                className="text-xs px-3 py-1 rounded-full border border-gray-200 text-gray-600 hover:bg-gray-50 disabled:opacity-40"
              >
                {s}
              </button>
            ))}
          </div>

          {/* Input */}
          <div className="px-4 py-3 border-t border-gray-100 flex items-end gap-2">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void handleSend();
                }
              }}
              rows={2}
              placeholder="예: 3번 슬라이드를 둘로 나눠주세요"
              disabled={isBusy}
              className="flex-1 resize-none rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#5146E5]/40 disabled:opacity-50"
            />
            <Button
              onClick={() => handleSend()}
              disabled={isBusy || !input.trim()}
              className="rounded-lg bg-[#5146E5] hover:bg-[#4338CA] text-white h-10 px-3"
            >
              <Send className="w-4 h-4" />
            </Button>
          </div>
        </div>

        {/* Right: live outline + confirm */}
        <div className="flex flex-col h-[calc(100vh-160px)]">
          <div className="flex-1 overflow-y-auto pr-1">
            <OutlineContent
              outlines={outlines}
              isLoading={isBusy && (!outlines || outlines.length === 0)}
              isStreaming={false}
              activeSlideIndex={null}
              highestActiveIndex={outlines ? outlines.length : 0}
              statusMessage=""
              onDragEnd={() => {}}
              onAddSlide={() => {}}
            />
          </div>
          <div className="pt-4 space-y-2">
            <Button
              onClick={handleSavePreset}
              disabled={isBusy || isSavingPreset || !hasExtracted || !conversationId}
              variant="outline"
              className="w-full rounded-[58px] py-3 px-5 font-semibold border-gray-300 disabled:opacity-50"
            >
              {isSavingPreset
                ? "규칙 요약 중…"
                : "💾 이 교정 규칙을 프리셋으로 저장"}
            </Button>
            <Button
              onClick={handleConfirm}
              disabled={isBusy || !outlines || outlines.length === 0}
              className="w-full rounded-[58px] py-3 px-5 font-semibold text-[#101323] disabled:opacity-50"
              style={{
                background:
                  "linear-gradient(270deg, #D5CAFC 2.4%, #E3D2EB 27.88%, #F4DCD3 69.23%, #FDE4C2 100%)",
              }}
            >
              이 아웃라인으로 확정하고 템플릿 선택 →
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default OutlineExtractPage;
