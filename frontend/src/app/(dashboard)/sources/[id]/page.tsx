'use client'

import { useRouter, useParams } from 'next/navigation'
import { useCallback, useEffect, useState } from 'react'
import type { PointerEvent as ReactPointerEvent } from 'react'
import { Button } from '@/components/ui/button'
import { ArrowLeft } from 'lucide-react'
import { useSourceChat } from '@/lib/hooks/useSourceChat'
import { ChatPanel } from '@/components/source/ChatPanel'
import { useNavigation } from '@/lib/hooks/use-navigation'
import { SourceDetailContent } from '@/components/source/SourceDetailContent'

const CHAT_WIDTH_STORAGE_KEY = 'source-chat-column-width'
const DEFAULT_CHAT_WIDTH = 480
// Wide range so users can collapse to a narrow column on big monitors or
// expand chat to take up most of the screen for long-form conversations.
const MIN_CHAT_WIDTH = 240
const MAX_CHAT_WIDTH = 1800

function clampChatWidth(width: number) {
  return Math.min(MAX_CHAT_WIDTH, Math.max(MIN_CHAT_WIDTH, width))
}

export default function SourceDetailPage() {
  const router = useRouter()
  const params = useParams()
  const sourceId = params?.id ? decodeURIComponent(params.id as string) : ''
  const navigation = useNavigation()

  // Initialize source chat
  const chat = useSourceChat(sourceId)

  const [chatWidth, setChatWidth] = useState(DEFAULT_CHAT_WIDTH)

  useEffect(() => {
    const storedWidth = window.localStorage.getItem(CHAT_WIDTH_STORAGE_KEY)
    if (!storedWidth) return

    const parsedWidth = Number(storedWidth)
    if (Number.isFinite(parsedWidth)) {
      setChatWidth(clampChatWidth(parsedWidth))
    }
  }, [])

  const updateChatWidth = useCallback((width: number) => {
    const nextWidth = clampChatWidth(width)
    setChatWidth(nextWidth)
    window.localStorage.setItem(CHAT_WIDTH_STORAGE_KEY, String(nextWidth))
  }, [])

  const handleChatResizeStart = useCallback((event: ReactPointerEvent<HTMLButtonElement>) => {
    event.preventDefault()

    const startX = event.clientX
    const startWidth = chatWidth
    const previousCursor = document.body.style.cursor
    const previousUserSelect = document.body.style.userSelect

    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'

    // Coalesce pointermove events into one paint frame. Without this, a
    // smooth mouse can fire 1000+ moves/s, each one triggering a React
    // setState + full re-render of the page. RAF caps it at ~60Hz.
    let pendingX: number | null = null
    let rafId: number | null = null

    const flush = () => {
      rafId = null
      if (pendingX === null) return
      updateChatWidth(startWidth - (pendingX - startX))
      pendingX = null
    }

    const handlePointerMove = (moveEvent: PointerEvent) => {
      pendingX = moveEvent.clientX
      if (rafId === null) {
        rafId = window.requestAnimationFrame(flush)
      }
    }

    const handlePointerUp = () => {
      if (rafId !== null) {
        window.cancelAnimationFrame(rafId)
        rafId = null
      }
      // Apply the final position so we never settle on a stale value.
      flush()
      document.body.style.cursor = previousCursor
      document.body.style.userSelect = previousUserSelect
      window.removeEventListener('pointermove', handlePointerMove)
      window.removeEventListener('pointerup', handlePointerUp)
    }

    window.addEventListener('pointermove', handlePointerMove)
    window.addEventListener('pointerup', handlePointerUp)
  }, [chatWidth, updateChatWidth])

  const handleBack = useCallback(() => {
    const returnPath = navigation.getReturnPath()
    router.push(returnPath)
    navigation.clearReturnTo()
  }, [navigation, router])

  return (
    <div className="flex flex-col h-screen">
      {/* Back button */}
      <div className="pt-6 pb-4 px-6">
        <Button
          variant="ghost"
          size="sm"
          onClick={handleBack}
          className="mb-4"
        >
          <ArrowLeft className="mr-2 h-4 w-4" />
          {navigation.getReturnLabel()}
        </Button>
      </div>

      {/* Main content: Source detail + Chat. On small screens stack vertically;
          on lg+ render as a flex row with a draggable resize handle. */}
      <div className="flex-1 flex flex-col lg:flex-row gap-6 overflow-hidden px-6">
        {/* Left column - Source detail */}
        <div className="flex-1 min-w-0 overflow-y-auto px-4 pb-6">
          <SourceDetailContent
            sourceId={sourceId}
            showChatButton={false}
            onClose={handleBack}
          />
        </div>

        {/* Resize handle - desktop only */}
        <button
          type="button"
          aria-label="Resize chat"
          onPointerDown={handleChatResizeStart}
          className="hidden lg:flex group relative w-3 flex-shrink-0 cursor-col-resize touch-none items-stretch justify-center rounded-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <span className="my-2 w-px rounded-full bg-border transition-colors group-hover:bg-primary group-focus-visible:bg-primary" />
        </button>

        {/* Right column - Chat. Width is user-resizable on desktop via the
            --chat-width CSS variable; stacks full-width on smaller viewports. */}
        <div
          className="w-full overflow-y-auto px-4 pb-6 min-w-0 lg:w-[var(--chat-width)] lg:flex-shrink-0"
          style={{ ['--chat-width' as string]: `${chatWidth}px` }}
        >
          <ChatPanel
            messages={chat.messages}
            isStreaming={chat.isStreaming}
            contextIndicators={chat.contextIndicators}
            onSendMessage={(message, model) => chat.sendMessage(message, model)}
            modelOverride={chat.currentSession?.model_override}
            onModelChange={(model) => {
              if (chat.currentSessionId) {
                chat.updateSession(chat.currentSessionId, { model_override: model })
              }
            }}
            sessions={chat.sessions}
            currentSessionId={chat.currentSessionId}
            onCreateSession={(title) => chat.createSession({ title })}
            onSelectSession={chat.switchSession}
            onUpdateSession={(sessionId, title) => chat.updateSession(sessionId, { title })}
            onDeleteSession={chat.deleteSession}
            loadingSessions={chat.loadingSessions}
          />
        </div>
      </div>
    </div>
  )
}
