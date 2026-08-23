<script setup>
defineProps({ visible: Boolean, message: String });
const emit = defineEmits(["confirm", "cancel"]);
</script>

<template>
  <transition name="fade">
    <div v-if="visible" class="modal-mask" @click.self="emit('cancel')">
      <div class="modal" role="dialog" aria-modal="true">
        <p class="modal-title">{{ message }}</p>
        <div class="modal-actions">
          <button class="modal-btn" @click="emit('cancel')">取消</button>
          <button class="modal-btn danger" @click="emit('confirm')">确定</button>
        </div>
      </div>
    </div>
  </transition>
</template>

<style scoped>
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}
.modal {
  background: #fff;
  border-radius: 12px;
  padding: 22px 24px 18px;
  min-width: 320px;
  max-width: 90vw;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.18);
}
.modal-title {
  font-size: 15px;
  color: var(--text, #1f2328);
  line-height: 1.5;
}
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 20px;
}
.modal-btn {
  padding: 7px 18px;
  border-radius: 8px;
  border: 1px solid var(--border, #d9dde3);
  background: #fff;
  font-size: 14px;
  cursor: pointer;
  color: var(--text, #1f2328);
  transition: border-color 0.15s;
}
.modal-btn:hover { border-color: var(--accent, #2b6cb0); }
.modal-btn.danger {
  background: #e0245e;
  border-color: #e0245e;
  color: #fff;
}
.modal-btn.danger:hover { background: #c11d50; }

.fade-enter-active, .fade-leave-active { transition: opacity 0.15s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
