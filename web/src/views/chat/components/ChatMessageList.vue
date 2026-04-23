<template>
	<div class="messages-area" ref="messagesAreaRef" @scroll="handleScroll">
		<!-- Loading State -->
		<div v-if="isLoading" class="loading-container">
			<div class="loading-spinner">
				<el-icon class="is-loading">
					<Loading/>
				</el-icon>
			</div>
			<span class="loading-text">正在加载...</span>
		</div>

		<!-- Messages -->
		<div v-else class="messages-container">
			<div
				v-for="block in expandedMessages"
				:key="block.id"
				class="message-block"
				:class="block.role"
			>
				<!-- User Message Block -->
				<div v-if="block.role === 'user'" class="user-message">
					<!-- Edit mode -->
					<div v-if="editingBlockId === block.id && block.type === 'text'" class="user-bubble edit-mode">
						<textarea
							ref="editTextareaRef"
							:value="editingContent"
							@input="handleEditingContentChange"
							class="edit-textarea"
							rows="2"
							@keydown="handleEditKeydown"
						></textarea>
						<div class="edit-actions">
							<button class="edit-btn cancel" @click="handleCancelEdit">取消</button>
							<button class="edit-btn confirm" @click="handleConfirmEdit">发送</button>
						</div>
					</div>
					<!-- Normal display -->
					<template v-else>
						<div class="user-bubble">
							<!-- Image block -->
							<div v-if="block.type === 'image'" class="image-block">
								<AttachmentPreview :part="block.part!"/>
							</div>
							<!-- Text block -->
							<div v-else class="user-text">
								<MarkdownRenderer :content="block.content"/>
							</div>
						</div>
					</template>
					<!-- Action buttons -->
					<div v-if="editingBlockId !== block.id && !sending" class="message-actions">
						<!-- Text block: edit + regenerate -->
						<template v-if="block.type === 'text'">
							<button class="action-icon-btn" @click="handleStartEdit(block.id, block)" title="编辑">
								<el-icon>
									<Edit/>
								</el-icon>
							</button>
							<button class="action-icon-btn" @click="handleRegenerate(block.originalIndex)" title="重新生成">
								<el-icon>
									<RefreshRight/>
								</el-icon>
							</button>
						</template>
						<!-- All blocks: delete -->
						<button class="action-icon-btn delete" @click="handleDelete(block.originalIndex)" title="删除">
							<el-icon>
								<Delete/>
							</el-icon>
						</button>
					</div>
				</div>

				<!-- Assistant Message -->
				<div v-else-if="block.role !== 'tool'" class="assistant-message">
					<div class="assistant-avatar">
						<el-icon>
							<Monitor/>
						</el-icon>
					</div>
					<div class="assistant-content">
						<div class="assistant-header">
							<div class="assistant-name">AI</div>
							<div v-if="!sending" class="message-actions">
								<button class="action-icon-btn" @click="handleCopy(block.message.content)" title="复制">
									<el-icon>
										<DocumentCopy/>
									</el-icon>
								</button>
								<button class="action-icon-btn delete" @click="handleDelete(block.originalIndex)" title="删除">
									<el-icon>
										<Delete/>
									</el-icon>
								</button>
							</div>
						</div>
						<!-- Error Message -->
						<div v-if="block.message.hasError" class="error-bubble">
							<el-icon class="error-icon">
								<WarningFilled/>
							</el-icon>
							<span class="error-text">{{ block.message.error }}</span>
							<button class="retry-btn" @click="handleRetry" title="重试">
								<el-icon>
									<RefreshRight/>
								</el-icon>
								重试
							</button>
						</div>
						<!-- Think Block -->
						<ThinkBlock
							v-if="block.message.hasThink"
							:content="block.message.thinkContent || ''"
							:tokens="estimateThinkTokens(block.message.thinkContent || '')"
							:default-collapsed="true"
							:force-expand="!block.message.content && (!block.message.toolCalls || block.message.toolCalls.length === 0)"
						/>
						<!-- Tool Calls Display -->
						<ToolCallDisplay
							v-if="block.message.toolCalls && block.message.toolCalls.length > 0"
							:tool-calls="block.message.toolCalls"
							:request-messages="getRequestMessagesForBlock(block)"
						/>
						<!-- Markdown Content -->
						<div v-if="block.message.content" class="assistant-bubble">
							<MarkdownRenderer :content="block.message.content"/>
						</div>
					</div>
				</div>
			</div>

			<!-- Streaming Message -->
			<div v-if="hasStreamingContent" class="message-block assistant">
				<div class="assistant-message">
					<div class="assistant-avatar" :class="{ thinking: isAnyToolRunning }">
						<el-icon v-if="isAnyToolRunning" class="is-loading">
							<Loading/>
						</el-icon>
						<el-icon v-else>
							<Monitor/>
						</el-icon>
					</div>
					<div class="assistant-content">
						<div class="assistant-name">AI</div>
						<!-- Streaming Think Block -->
						<ThinkBlock
							v-if="streamingThink"
							:content="streamingThink"
							:default-collapsed="true"
							:force-expand="!streamingContent && streamingToolCalls.length === 0"
						/>
						<!-- Streaming Tool Calls Display -->
						<ToolCallDisplay
							v-if="streamingToolCalls.length > 0"
							:tool-calls="streamingToolCalls"
							:request-messages="requestMessages"
						/>
						<!-- Tool Executing Indicator -->
						<div v-if="isAnyToolRunning" class="tool-executing-indicator">
							<el-icon class="is-loading">
								<Loading/>
							</el-icon>
							<span>正在执行工具...</span>
						</div>
						<!-- Streaming Markdown Content -->
						<div v-if="streamingContent" class="assistant-bubble">
							<MarkdownRenderer :content="streamingContent" :streaming="sending"/>
							<span class="cursor" v-if="sending">▌</span>
						</div>
					</div>
				</div>
			</div>

			<!-- Thinking State -->
			<div
				v-if="sending && !hasStreamingContent"
				class="message-block assistant"
			>
				<div class="assistant-message">
					<div class="assistant-avatar thinking">
						<el-icon class="is-loading">
							<Loading/>
						</el-icon>
					</div>
					<div class="assistant-content">
						<div class="assistant-name">AI</div>
						<div class="assistant-bubble thinking">
							<div class="thinking-indicator">
								<span></span><span></span><span></span>
							</div>
							<span class="thinking-text">正在思考...</span>
						</div>
					</div>
				</div>
			</div>
		</div>
	</div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import { Monitor, Loading, Edit, RefreshRight, Delete, DocumentCopy, WarningFilled } from '@element-plus/icons-vue'
import MarkdownRenderer from '@/components/chat/MarkdownRenderer.vue'
import ThinkBlock from '@/components/chat/ThinkBlock.vue'
import ToolCallDisplay from '@/components/chat/ToolCallDisplay.vue'
import AttachmentPreview from '@/components/chat/AttachmentPreview.vue'
import { estimateThinkTokens } from '@/utils/messageParser'
import type { ExpandedMessageBlock } from '@/composables/useChatMessages'
import type { ExtendedMessage } from '@/composables/useChatConversation'
import type { ToolCallResult } from '@/types/tool'

interface Props {
	expandedMessages: ExpandedMessageBlock[]
	messages: ExtendedMessage[]
	sending: boolean
	isLoading: boolean
	streamingContent: string
	streamingThink: string
	streamingToolCalls: ToolCallResult[]
	isAnyToolRunning: boolean
	editingBlockId: string | number | null
	editingContent: string
	isUserAtBottom: boolean
	userHasScrolledDuringOutput: boolean
}

interface Emits {
	(e: 'update:editingBlockId', value: string | number | null): void
	(e: 'update:editingContent', value: string): void
	(e: 'update:isUserAtBottom', value: boolean): void
	(e: 'update:userHasScrolledDuringOutput', value: boolean): void
	(e: 'startEdit', blockId: string | number, block: ExpandedMessageBlock): void
	(e: 'cancelEdit'): void
	(e: 'confirmEdit'): void
	(e: 'regenerate', index: number): void
	(e: 'delete', index: number): void
	(e: 'copy', content: string): void
	(e: 'retry'): void
	(e: 'editKeydown', event: KeyboardEvent): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const messagesAreaRef = ref<HTMLElement | null>(null)
const editTextareaRef = ref<HTMLTextAreaElement | null>(null)

// Computed
const hasStreamingContent = computed(() =>
	props.streamingContent.trim() ||
	props.streamingThink ||
	props.streamingToolCalls.length > 0
)

const requestMessages = computed(() =>
	props.messages.map(m => ({ role: m.role, content: m.content }))
)

// Methods
const handleScroll = () => {
	if (messagesAreaRef.value) {
		const { scrollTop, scrollHeight, clientHeight } = messagesAreaRef.value
		const atBottom = scrollHeight - scrollTop - clientHeight < 150
		emit('update:isUserAtBottom', atBottom)

		if (!atBottom && props.sending) {
			emit('update:userHasScrolledDuringOutput', true)
		}
	}
}

const scrollToBottom = () => {
	if (messagesAreaRef.value && !props.userHasScrolledDuringOutput) {
		messagesAreaRef.value.scrollTop = messagesAreaRef.value.scrollHeight
	}
}

const getRequestMessagesForBlock = (block: ExpandedMessageBlock) => {
	return props.messages.slice(0, block.originalIndex + 1).map(m => ({
		role: m.role,
		content: m.content
	}))
}

// Auto resize edit textarea with content change
const handleEditingContentChange = (event: Event) => {
	const target = event.target as HTMLTextAreaElement
	emit('update:editingContent', target.value)
	// Auto resize
	target.style.height = 'auto'
	target.style.height = Math.min(target.scrollHeight, 200) + 'px'
}

const handleStartEdit = (blockId: string | number, block: ExpandedMessageBlock) => {
	emit('startEdit', blockId, block)
}

const handleCancelEdit = () => {
	emit('cancelEdit')
}

const handleConfirmEdit = () => {
	emit('confirmEdit')
}

const handleEditKeydown = (e: KeyboardEvent) => {
	emit('editKeydown', e)
}

const handleRegenerate = (index: number) => {
	emit('regenerate', index)
}

const handleDelete = (index: number) => {
	emit('delete', index)
}

const handleCopy = (content: string) => {
	emit('copy', content)
}

const handleRetry = () => {
	emit('retry')
}

// Watch for new messages to scroll
watch(() => props.expandedMessages.length, () => {
	nextTick(() => {
		if (props.isUserAtBottom) {
			scrollToBottom()
		}
	})
})

// Watch streaming content
watch(() => props.streamingContent, () => {
	if (props.isUserAtBottom && !props.userHasScrolledDuringOutput) {
		scrollToBottom()
	}
})

// Expose scrollToBottom for parent
defineExpose({ scrollToBottom, messagesAreaRef, editTextareaRef })
</script>

<style scoped>
.messages-area {
	flex: 1;
	overflow-y: auto;
	padding: 20px;
	background: #f8f9fa;
}

.loading-container {
	height: 100%;
	display: flex;
	flex-direction: column;
	align-items: center;
	justify-content: center;
	gap: 16px;
}

.loading-spinner {
	width: 48px;
	height: 48px;
	display: flex;
	align-items: center;
	justify-content: center;
	background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
	border-radius: 50%;
	color: white;
}

.loading-spinner .el-icon {
	font-size: 24px;
}

.loading-text {
	font-size: 14px;
	color: #666;
}

.messages-container {
	max-width: 800px;
	margin: 0 auto;
	display: flex;
	flex-direction: column;
	gap: 16px;
}

.message-block {
	display: flex;
	gap: 12px;
}

.message-block.user {
	flex-direction: row-reverse;
}

.user-message {
	display: flex;
	flex-direction: column;
	align-items: flex-end;
	gap: 8px;
	max-width: 70%;
	min-width: 70%;
}

.user-bubble {
	max-width: 100%;
	padding: 12px 16px;
	background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
	color: white;
	border-radius: 16px 16px 4px 16px;
}

.user-bubble.edit-mode {
	background: white;
	border: 1px solid #e0e0e0;
	color: #333;
	padding: 12px;
	min-width: 300px;
	width: 100%;
}

.edit-textarea {
	width: 100%;
	min-height: 14rem;
	max-height: 200px;
	padding: 10px 12px;
	border: 1px solid #d0d0d0;
	border-radius: 8px;
	font-size: 14px;
	line-height: 1.5;
	resize: none;
	outline: none;
	overflow-y: auto;
	font-family: inherit;
}

.edit-textarea:focus {
	border-color: #667eea;
}

.edit-actions {
	display: flex;
	gap: 8px;
	margin-top: 8px;
}

.edit-btn {
	padding: 6px 12px;
	border: none;
	border-radius: 6px;
	font-size: 13px;
	cursor: pointer;
}

.edit-btn.cancel {
	background: #f0f0f0;
	color: #666;
}

.edit-btn.confirm {
	background: #667eea;
	color: white;
}

.user-text {
	word-break: break-word;
}

.image-block {
	max-width: 200px;
}

.assistant-message {
	display: flex;
	gap: 12px;
	max-width: 85%;
}

.assistant-avatar {
	display: flex;
	align-items: center;
	justify-content: center;
	width: 36px;
	height: 36px;
	background: #f0f0f0;
	border-radius: 8px;
	color: #666;
}

.assistant-avatar.thinking {
	background: #e8f4fd;
	color: #667eea;
}

.assistant-content {
	flex: 1;
	min-width: 0;
}

.assistant-header {
	display: flex;
	align-items: center;
	justify-content: space-between;
	margin-bottom: 8px;
}

.assistant-name {
	font-weight: 600;
	color: #333;
}

.message-actions {
	display: flex;
	gap: 4px;
	opacity: 0;
	transition: opacity 0.2s;
}

.message-block:hover .message-actions {
	opacity: 1;
}

.action-icon-btn {
	display: flex;
	align-items: center;
	justify-content: center;
	width: 28px;
	height: 28px;
	background: #f0f0f0;
	border: none;
	border-radius: 6px;
	cursor: pointer;
	color: #666;
	transition: background 0.2s;
}

.action-icon-btn:hover {
	background: #e0e0e0;
}

.action-icon-btn.delete:hover {
	background: #fee2e2;
	color: #ff4d4f;
}

.error-bubble {
	display: flex;
	align-items: center;
	gap: 8px;
	padding: 12px 16px;
	background: #fee2e2;
	border-radius: 8px;
	color: #ff4d4f;
}

.error-icon {
	font-size: 16px;
}

.error-text {
	flex: 1;
	font-size: 13px;
}

.retry-btn {
	display: flex;
	align-items: center;
	gap: 4px;
	padding: 6px 12px;
	background: white;
	border: none;
	border-radius: 6px;
	font-size: 13px;
	cursor: pointer;
	color: #ff4d4f;
}

.assistant-bubble {
	padding: 12px 16px;
	background: white;
	border-radius: 12px;
	border: 1px solid #e0e0e0;
	word-break: break-word;
}

.assistant-bubble.thinking {
	display: flex;
	align-items: center;
	gap: 8px;
}

.thinking-indicator {
	display: flex;
	gap: 4px;
}

.thinking-indicator span {
	width: 8px;
	height: 8px;
	background: #667eea;
	border-radius: 50%;
	animation: thinking 1.4s infinite ease-in-out both;
}

.thinking-indicator span:nth-child(1) {
	animation-delay: -0.32s;
}

.thinking-indicator span:nth-child(2) {
	animation-delay: -0.16s;
}

@keyframes thinking {
	0%, 80%, 100% {
		transform: scale(0);
	}
	40% {
		transform: scale(1);
	}
}

.thinking-text {
	font-size: 13px;
	color: #666;
}

.cursor {
	color: #667eea;
	animation: blink 1s infinite;
}

@keyframes blink {
	0%, 50% {
		opacity: 1;
	}
	51%, 100% {
		opacity: 0;
	}
}

.tool-executing-indicator {
	display: flex;
	align-items: center;
	gap: 8px;
	padding: 12px;
	background: #f8f9fa;
	border-radius: 8px;
	font-size: 13px;
	color: #666;
}

.is-loading {
	animation: spin 1s linear infinite;
}

@keyframes spin {
	from {
		transform: rotate(0deg);
	}
	to {
		transform: rotate(360deg);
	}
}

@media (max-width: 768px) {
	.user-message,
	.assistant-message {
		max-width: 90%;
	}

	.messages-area {
		padding: 12px;
	}
}
</style>
