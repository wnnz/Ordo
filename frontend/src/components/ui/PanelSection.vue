<script setup lang="ts">
withDefaults(defineProps<{
  title?: string
  description?: string
}>(), {
  title: '',
  description: '',
})
</script>

<template>
  <section class="surface rounded-xl p-5">
    <header
      v-if="title || description || $slots.icon || $slots.actions"
      class="flex items-start gap-3"
    >
      <slot name="icon" />
      <div v-if="title || description" class="min-w-0">
        <h2 v-if="title" class="font-semibold">{{ title }}</h2>
        <p v-if="description" class="muted mt-1 text-xs">{{ description }}</p>
      </div>
      <div v-if="$slots.actions" class="ml-auto flex shrink-0 items-center gap-2">
        <slot name="actions" />
      </div>
    </header>
    <div :class="title || description || $slots.icon || $slots.actions ? 'mt-5' : ''">
      <slot />
    </div>
  </section>
</template>
