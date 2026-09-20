<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  name?: string | null
  size?: 'sm' | 'md' | 'lg'
}>(), {
  name: '',
  size: 'md',
})

const initial = computed(() => props.name?.trim().charAt(0).toUpperCase() || '?')
const sizeClass = computed(() => ({
  sm: 'h-7 w-7 text-xs',
  md: 'h-9 w-9 text-xs',
  lg: 'h-11 w-11 text-sm',
}[props.size]))
</script>

<template>
  <span
    class="flex shrink-0 items-center justify-center rounded-full bg-[var(--primary-soft)] font-medium text-[var(--primary)]"
    :class="sizeClass"
  >
    {{ initial }}
  </span>
</template>
