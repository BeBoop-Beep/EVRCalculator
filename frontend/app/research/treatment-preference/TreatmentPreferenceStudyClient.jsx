"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

const SESSION_KEY = "index:treatment-preference-v1:session";
const DRAFT_KEY = "index:treatment-preference-v1:draft";

function getOrCreateSessionId() {
  const existing = window.localStorage.getItem(SESSION_KEY);
  if (existing) return existing;
  const created = window.crypto.randomUUID();
  window.localStorage.setItem(SESSION_KEY, created);
  return created;
}

function saveDraft(blockId, answers) {
  window.localStorage.setItem(DRAFT_KEY, JSON.stringify({ blockId, answers }));
}

function readDraft(blockId) {
  try {
    const parsed = JSON.parse(window.localStorage.getItem(DRAFT_KEY) || "null");
    if (!parsed || parsed.blockId !== blockId || typeof parsed.answers !== "object") return {};
    return parsed.answers || {};
  } catch {
    return {};
  }
}

export default function TreatmentPreferenceStudyClient() {
  const [sessionId, setSessionId] = useState("");
  const [block, setBlock] = useState(null);
  const [answers, setAnswers] = useState({});
  const [index, setIndex] = useState(0);
  const [reviewing, setReviewing] = useState(false);
  const [status, setStatus] = useState("loading");
  const [message, setMessage] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const loadBlock = useCallback(async (sid) => {
    setStatus("loading");
    setMessage("");
    try {
      const response = await fetch(
        `/api/research/treatment-preference-v1/block?sessionId=${encodeURIComponent(sid)}`,
        { cache: "no-store" },
      );
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.message || "Study unavailable.");

      if (payload.status !== "ready") {
        setBlock(null);
        setAnswers({});
        setStatus(payload.status || "complete");
        setMessage(payload.message || "Thank you.");
        window.localStorage.removeItem(DRAFT_KEY);
        return;
      }

      const restored = readDraft(payload.blockId);
      setBlock(payload);
      setAnswers(restored);
      const firstUnanswered = payload.questions.findIndex((q) => !restored[q.pairId]);
      if (firstUnanswered === -1) {
        setIndex(payload.questions.length - 1);
        setReviewing(true);
      } else {
        setIndex(firstUnanswered);
        setReviewing(false);
      }
      setStatus("ready");
    } catch (error) {
      setStatus("error");
      setMessage(error instanceof Error ? error.message : "Study unavailable.");
    }
  }, []);

  useEffect(() => {
    const sid = getOrCreateSessionId();
    setSessionId(sid);
    loadBlock(sid);
  }, [loadBlock]);

  const questions = block?.questions || [];
  const current = questions[index] || null;
  const answeredCount = useMemo(
    () => questions.reduce((count, q) => count + (answers[q.pairId] ? 1 : 0), 0),
    [answers, questions],
  );
  const allAnswered = questions.length > 0 && answeredCount === questions.length;

  function choose(responseValue) {
    if (!current || reviewing) return;
    const next = { ...answers, [current.pairId]: responseValue };
    setAnswers(next);
    saveDraft(block.blockId, next);
    if (index < questions.length - 1) {
      setIndex(index + 1);
    } else {
      setReviewing(true);
    }
  }

  function goBack() {
    if (reviewing) {
      setReviewing(false);
      setIndex(questions.length - 1);
      return;
    }
    if (index > 0) setIndex(index - 1);
  }

  async function submit() {
    if (!block || !allAnswered || submitting) return;
    setSubmitting(true);
    setMessage("");
    try {
      const response = await fetch("/api/research/treatment-preference-v1/submit", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          sessionId,
          blockId: block.blockId,
          claimToken: block.claimToken,
          answers: questions.map((q) => ({
            pairId: q.pairId,
            response: answers[q.pairId],
          })),
        }),
      });
      const payload = await response.json();
      if (!response.ok) {
        if (response.status === 409) {
          window.localStorage.removeItem(DRAFT_KEY);
          await loadBlock(sessionId);
          return;
        }
        throw new Error(payload.message || "Unable to submit responses.");
      }
      window.localStorage.removeItem(DRAFT_KEY);
      setStatus("submitted");
      setBlock(null);
      setMessage(payload.message || "Thank you. Your responses were recorded.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to submit responses.");
    } finally {
      setSubmitting(false);
    }
  }

  if (status === "loading") {
    return (
      <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-raised)] p-8 text-center text-[var(--text-secondary)]">
        Loading the blinded comparison block…
      </div>
    );
  }

  if (status === "submitted" || status === "complete") {
    return (
      <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-raised)] p-8 text-center">
        <h2 className="text-2xl font-semibold text-[var(--text-primary)]">Thank you</h2>
        <p className="mx-auto mt-3 max-w-xl text-[var(--text-secondary)]">{message}</p>
      </div>
    );
  }

  if (status === "error" || !block || !current) {
    return (
      <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-raised)] p-8 text-center">
        <h2 className="text-xl font-semibold text-[var(--text-primary)]">Study unavailable</h2>
        <p className="mt-3 text-[var(--text-secondary)]">{message || "Please try again."}</p>
        <button
          type="button"
          onClick={() => sessionId && loadBlock(sessionId)}
          className="mt-5 rounded-lg border border-[var(--border-subtle)] px-4 py-2 font-semibold text-[var(--text-primary)]"
        >
          Try again
        </button>
      </div>
    );
  }

  if (reviewing) {
    return (
      <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-raised)] p-6 sm:p-8">
        <p className="text-sm font-semibold uppercase tracking-[.14em] text-[var(--accent)]">
          12 of 12 complete
        </p>
        <h2 className="mt-2 text-2xl font-semibold text-[var(--text-primary)]">Ready to submit?</h2>
        <p className="mt-3 text-[var(--text-secondary)]">
          Your choices are recorded as anonymous visual-preference responses. No market values or aggregate results are shown during the study.
        </p>
        {message ? <p className="mt-4 text-sm text-[var(--text-secondary)]">{message}</p> : null}
        <div className="mt-7 flex flex-col gap-3 sm:flex-row">
          <button
            type="button"
            onClick={goBack}
            className="rounded-lg border border-[var(--border-subtle)] px-5 py-3 font-semibold text-[var(--text-primary)]"
          >
            Review last comparison
          </button>
          <button
            type="button"
            disabled={!allAnswered || submitting}
            onClick={submit}
            className="rounded-lg bg-[var(--accent)] px-5 py-3 font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            {submitting ? "Submitting…" : "Submit responses"}
          </button>
        </div>
      </div>
    );
  }

  const selected = answers[current.pairId];
  const progress = Math.round(((index + 1) / questions.length) * 100);

  return (
    <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-raised)] p-4 sm:p-6 lg:p-8">
      <div className="flex items-center justify-between gap-4">
        <p className="text-sm font-semibold text-[var(--text-secondary)]">
          Comparison {index + 1} of {questions.length}
        </p>
        <p className="text-sm text-[var(--text-secondary)]">{answeredCount} answered</p>
      </div>
      <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-[var(--surface-muted)]">
        <div className="h-full bg-[var(--accent)] transition-[width]" style={{ width: `${progress}%` }} />
      </div>

      <h2 className="mx-auto mt-7 max-w-2xl text-center text-xl font-semibold text-[var(--text-primary)] sm:text-2xl">
        Which version would you rather own for the artwork/presentation itself?
      </h2>
      <p className="mx-auto mt-2 max-w-2xl text-center text-sm leading-6 text-[var(--text-secondary)]">
        Ignore market value, pull rates, rankings, and what you think either card may be worth.
      </p>

      <div className="mt-7 grid grid-cols-2 gap-3 sm:gap-6">
        <button
          type="button"
          aria-label="Choose the left card"
          onClick={() => choose("LEFT")}
          className="group rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-base)] p-2 transition hover:border-[var(--accent)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)]"
        >
          <img
            src={current.leftImageUrl}
            alt="Left card option"
            className="mx-auto h-auto w-full max-w-[360px] rounded-lg"
            draggable={false}
            referrerPolicy="no-referrer"
          />
          <span className="mt-3 block pb-1 text-sm font-semibold text-[var(--text-primary)]">Choose left</span>
        </button>

        <button
          type="button"
          aria-label="Choose the right card"
          onClick={() => choose("RIGHT")}
          className="group rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-base)] p-2 transition hover:border-[var(--accent)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)]"
        >
          <img
            src={current.rightImageUrl}
            alt="Right card option"
            className="mx-auto h-auto w-full max-w-[360px] rounded-lg"
            draggable={false}
            referrerPolicy="no-referrer"
          />
          <span className="mt-3 block pb-1 text-sm font-semibold text-[var(--text-primary)]">Choose right</span>
        </button>
      </div>

      <div className="mt-5 flex flex-col items-center justify-between gap-3 sm:flex-row">
        <button
          type="button"
          onClick={goBack}
          disabled={index === 0}
          className="order-2 rounded-lg px-4 py-2 text-sm font-semibold text-[var(--text-secondary)] disabled:opacity-30 sm:order-1"
        >
          Back
        </button>
        <button
          type="button"
          onClick={() => choose("TIE")}
          className="order-1 rounded-lg border border-[var(--border-subtle)] px-5 py-2.5 text-sm font-semibold text-[var(--text-primary)] sm:order-2"
        >
          No preference / effectively tied
        </button>
        <span className="order-3 min-w-20 text-right text-xs text-[var(--text-secondary)]">
          {selected ? "Saved" : ""}
        </span>
      </div>
    </div>
  );
}
