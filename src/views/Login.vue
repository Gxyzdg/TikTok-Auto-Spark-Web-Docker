<template>
  <div class="login-container">
    <div class="login-card">
      <div class="login-brand">
        <div class="brand-logo"><FlameIcon /></div>
        <h1 class="brand-title">抖音火花助手</h1>
        <p class="brand-sub">抖音好友火花自动续期 · 管理后台</p>
      </div>

      <el-form
        ref="loginFormRef"
        :model="loginForm"
        :rules="loginRules"
        class="login-form"
        @keyup.enter="handleLogin"
      >
        <el-form-item prop="username">
          <el-input
            v-model="loginForm.username"
            placeholder="请输入用户名"
            size="large"
            :prefix-icon="User"
          />
        </el-form-item>

        <el-form-item prop="password">
          <el-input
            v-model="loginForm.password"
            type="password"
            placeholder="请输入密码"
            size="large"
            :prefix-icon="Lock"
            show-password
          />
        </el-form-item>

        <el-button
          type="primary"
          size="large"
          :loading="loading"
          class="login-button"
          @click="handleLogin"
        >
          {{ loading ? '登录中…' : '登 录' }}
        </el-button>
      </el-form>

      <p class="login-footer">仅供内网学习使用</p>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { User, Lock } from '@element-plus/icons-vue'
import { useUserStore } from '../stores/user'
import FlameIcon from '../components/FlameIcon.vue'

const router = useRouter()
const userStore = useUserStore()

const loginFormRef = ref(null)
const loading = ref(false)

const loginForm = reactive({
  username: '',
  password: ''
})

const loginRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' }
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' }
  ]
}

const handleLogin = async () => {
  if (loading.value) return
  if (!loginFormRef.value) return

  await loginFormRef.value.validate(async (valid) => {
    if (valid) {
      loading.value = true
      try {
        const result = await userStore.login(loginForm.username, loginForm.password)
        if (result.success) {
          ElMessage.success(result.message)
          router.push('/')
        } else {
          ElMessage.error(result.message)
        }
      } catch (error) {
        ElMessage.error('登录失败')
      } finally {
        loading.value = false
      }
    }
  })
}
</script>

<style scoped>
.login-container {
  position: relative;
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 24px;
  background: var(--bg);
  background-image: var(--bg-accent);
  background-attachment: fixed;
  background-repeat: no-repeat;
}

.login-card {
  position: relative;
  z-index: 1;
  width: 100%;
  max-width: 380px;
  padding: 32px 30px 22px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-md);
  animation: fadeInUp 0.32s var(--ease) both;
}

.login-brand {
  text-align: center;
  margin-bottom: 24px;
}

.brand-logo {
  width: 48px;
  height: 48px;
  margin: 0 auto 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  color: #fff;
  border-radius: var(--radius-lg);
  background: var(--gradient);
  box-shadow: 0 6px 16px color-mix(in srgb, var(--primary) 28%, transparent);
}

.brand-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-1);
  letter-spacing: -0.005em;
}

.brand-sub {
  margin-top: 4px;
  font-size: 12.5px;
  color: var(--text-3);
}

.login-form :deep(.el-input__wrapper) {
  border-radius: var(--radius-md);
  background: var(--surface-muted);
  box-shadow: none;
  padding: 3px 12px;
  transition: background-color var(--dur) ease, box-shadow var(--dur) ease;
}

.login-form :deep(.el-input__wrapper.is-focus) {
  background: var(--surface);
  box-shadow: 0 0 0 1px var(--primary) inset;
}

.login-form :deep(.el-input__inner) {
  font-size: 14px;
  color: var(--text-1);
}

.login-button {
  width: 100%;
  height: 42px;
  margin-top: 4px;
  font-size: 14.5px;
  font-weight: 600;
  border-radius: var(--radius-md);
  box-shadow: 0 4px 14px color-mix(in srgb, var(--primary) 24%, transparent);
}

.login-button:hover {
  transform: translateY(-1px);
  box-shadow: 0 6px 18px color-mix(in srgb, var(--primary) 32%, transparent);
}

.login-button:active {
  transform: translateY(0);
}

.login-footer {
  margin-top: 18px;
  text-align: center;
  font-size: 11.5px;
  color: var(--text-faint);
}

@media (max-width: 480px) {
  .login-card {
    padding: 26px 22px 18px;
  }
}
</style>
