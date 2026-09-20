<script setup lang="ts">
const emit = defineEmits<{
  click: [event: MouseEvent]
}>()

withDefaults(defineProps<{
  selected?: boolean
  disabled?: boolean
  type?: 'button' | 'submit' | 'reset'
}>(), {
  selected: false,
  disabled: false,
  type: 'button',
})
</script>

<template>
  <button
    :type="type"
    :disabled="disabled"
    class="card-hover rounded-lg border transition-colors"
    :class="selected ? 'border-[var(--primary)] bg-[var(--primary-soft)] text-[var(--primary)]' : 'border-[var(--border)]'"
    @click="emit('click', $event)"
  >
    <slot />
  </button>
</template>
