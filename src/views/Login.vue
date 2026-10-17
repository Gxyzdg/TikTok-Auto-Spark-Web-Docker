<template>
  <div class="login-container">
    <div class="login-orb login-orb--a"></div>
    <div class="login-orb login-orb--b"></div>

    <div class="login-card">
      <div class="login-brand">
        <div class="brand-logo"><FlameIcon /></div>
        <h1 class="brand-title">抖音火花助手</h1>
        <p class="brand-sub">好友火花自动续期 · 管理后台</p>
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
            placeholder="用户名"
            size="large"
            :prefix-icon="User"
            autocomplete="username"
          />
        </el-form-item>

        <el-form-item prop="password">
          <el-input
            v-model="loginForm.password"
            type="password"
            placeholder="密码"
            size="large"
            :prefix-icon="Lock"
            show-password
            autocomplete="current-password"
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

      <div class="login-hint">
        <el-icon class="hint-icon"><InfoFilled /></el-icon>
        <div>
          <p class="hint-title">第一次使用？</p>
          <p class="hint-desc">
            初始密码是随机生成的一次性密码，可在容器日志中找到：
            <code>docker logs 容器名</code>，搜索「一次性管理员密码」。
          </p>
        </div>
      </div>

      <p class="login-footer">仅供内网学习使用 · {{ version }}</p>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { User, Lock, InfoFilled } from '@element-plus/icons-vue'
import { useUserStore } from '../stores/user'
import { APP_VERSION } from '../config'
import FlameIcon from '../components/FlameIcon.vue'

const router = useRouter()
const userStore = useUserStore()

const version = APP_VERSION
const loginFormRef = ref(null)
const loading = ref(false)

const loginForm = reactive({
  username: 'admin',
  password: ''
})

const loginRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }]
}

const handleLogin = async () => {
  if (loading.value) return
  if (!loginFormRef.value) return

  await loginFormRef.value.validate(async (valid) => {
    if (valid) {
      loading.value = true
      try {
        const result = await userStore.login(loginForm.username.trim(), loginForm.password)
        if (result.success) {
          if (result.mustChangePassword) {
            // 一次性初始密码：把刚输入的密码带到改密页预填，避免用户再抄一遍
            try {
              sessionStorage.setItem('spark_setup_pwd', loginForm.password)
            } catch (e) {}
            ElMessage.warning('请先设置新密码后再使用后台')
            router.replace('/setup')
          } else {
            ElMessage.success('登录成功')
            router.replace('/')
          }
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
  overflow: hidden;
  background: var(--bg);
  background-image: var(--bg-accent);
  background-attachment: fixed;
  background-repeat: no-repeat;
}

/* 背景光斑：让登录页看起来更有层次（纯装饰，不影响交互） */
.login-orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(70px);
  opacity: 0.5;
  pointer-events: none;
}
.login-orb--a {
  width: 380px;
  height: 380px;
  top: -120px;
  left: -100px;
  background: color-mix(in srgb, var(--primary) 45%, transparent);
}
.login-orb--b {
  width: 320px;
  height: 320px;
  bottom: -110px;
  right: -80px;
  background: color-mix(in srgb, var(--primary) 22%, #7c5cff 78%);
  opacity: 0.32;
}

.login-card {
  position: relative;
  z-index: 1;
  width: 100%;
  max-width: 392px;
  padding: 34px 32px 22px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-md);
  backdrop-filter: blur(6px);
  animation: fadeInUp 0.32s var(--ease) both;
}

.login-brand {
  text-align: center;
  margin-bottom: 26px;
}

.brand-logo {
  width: 52px;
  height: 52px;
  margin: 0 auto 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 26px;
  color: #fff;
  border-radius: 16px;
  background: var(--gradient);
  box-shadow: 0 10px 24px color-mix(in srgb, var(--primary) 32%, transparent);
}

.brand-title {
  font-size: 19px;
  font-weight: 600;
  color: var(--text-1);
  letter-spacing: -0.01em;
}

.brand-sub {
  margin-top: 5px;
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
  height: 44px;
  margin-top: 6px;
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 0.08em;
  border-radius: var(--radius-md);
  background: var(--gradient);
  border: none;
  box-shadow: 0 8px 20px color-mix(in srgb, var(--primary) 26%, transparent);
}

.login-button:hover {
  transform: translateY(-1px);
  box-shadow: 0 10px 24px color-mix(in srgb, var(--primary) 34%, transparent);
}

.login-button:active {
  transform: translateY(0);
}

.login-hint {
  display: flex;
  gap: 10px;
  margin-top: 22px;
  padding: 12px 14px;
  border-radius: var(--radius-md);
  background: color-mix(in srgb, var(--primary) 6%, var(--surface-muted));
  border: 1px dashed color-mix(in srgb, var(--primary) 28%, var(--border));
}

.hint-icon {
  flex: none;
  margin-top: 2px;
  color: var(--primary);
  font-size: 15px;
}

.hint-title {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--text-1);
}

.hint-desc {
  margin-top: 3px;
  font-size: 11.5px;
  line-height: 1.6;
  color: var(--text-3);
}

.hint-desc code {
  padding: 1px 5px;
  border-radius: 4px;
  background: color-mix(in srgb, var(--text-1) 8%, transparent);
  font-size: 11px;
  word-break: break-all;
}

.login-footer {
  margin-top: 16px;
  text-align: center;
  font-size: 11.5px;
  color: var(--text-faint);
}

@media (max-width: 480px) {
  .login-card {
    padding: 28px 22px 18px;
  }
}
</style>
