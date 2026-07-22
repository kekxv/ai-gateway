<script setup lang="ts">
import { computed } from 'vue'
import { ElTag, type TagProps } from 'element-plus'
import 'element-plus/theme-chalk/el-tag.css'

export type StatusValue = 'enabled' | 'disabled' | 'healthy' | 'warning' | 'error' | 'pending'

const props = defineProps<{
  status: StatusValue
  label?: string
}>()

const statusDetails: Record<
  StatusValue,
  { label: string; type: NonNullable<TagProps['type']> }
> = {
  enabled: { label: '已启用', type: 'success' },
  disabled: { label: '已停用', type: 'info' },
  healthy: { label: '正常', type: 'success' },
  warning: { label: '需关注', type: 'warning' },
  error: { label: '异常', type: 'danger' },
  pending: { label: '处理中', type: 'primary' },
}

const details = computed(() => statusDetails[props.status])
</script>

<template>
  <ElTag :type="details.type" effect="light" round>{{ label ?? details.label }}</ElTag>
</template>
