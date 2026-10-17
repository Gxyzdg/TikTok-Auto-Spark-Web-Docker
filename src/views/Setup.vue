<template>
  <div class="setup-container">
    <div class="setup-orb setup-orb--a"></div>
    <div class="setup-orb setup-orb--b"></div>

    <div class="setup-card">
      <div class="setup-head">
        <div class="setup-badge">
          <el-icon><CircleCheckFilled /></el-icon>
        </div>
        <h1 class="setup-title">首次登录 · 安全设置</h1>
        <p class="setup-sub">你正在使用一次性初始密码，请先设置自己的密码后再进入后台</p>
      </div>

      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-position="top"
        class="setup-form"
        @keyup.enter="handleSubmit"
      >
        <el-form-item label="用户名" prop="username">
          <el-input v-model="form.username" size="large" :prefix-icon="User" maxlength="20" />
          <p class="field-tip">默认 admin，可改成你自己喜欢的用户名（2-20 个字符）</p>
        </el-form-item>

        <el-form-item label="新密码" prop="newPassword">
          <el-input
            v-model="form.newPassword"
            type="password"
            size="large"
            :prefix-icon="Lock"
            show-password
            placeholder="至少 8 位，建议包含字母和数字"
          />
          <div class="strength">
            <span
              v-for="i in 4"
              :key="i"
              class="strength-bar"
              :class="[`level-${strength}`, { active: i <= strength }]"
            ></span>
            <span class="strength-text">{{ strengthText }}</span>
          </div>
        </el-form-item>

        <el-form-item label="确认新密码" prop="confirmPassword">
          <el-input
            v-model="form.confirmPassword"
            type="password"
            size="large"
            :prefix-icon="Lock"
            show-password
            placeholder="再次输入新密码"
          />
        </el-form-item>

        <el-collapse v-model="advancedOpen" class="advanced">
          <el-collapse-item name="adv">
            <template #title>
              <span class="advanced-title">当前密码（已自动填入，可留空）</span>
            </template>
            <el-input
              v-model="form.oldPassword"
              type="password"
              size="large"
              show-password
              placeholder="一次性初始密码"
            />
            <p class="field-tip">
              用于校验身份；若已被清空，请填写日志里的「一次性管理员密码」或你最近设置的密码。
            </p>
          </el-collapse-item>
        </el-collapse>

        <el-alert type="info" :closable="false" class="setup-alert" show-icon>
          <template #title>
            <span class="alert-text">修改后 noVNC 密码会同步更新，Web 后台与 noVNC 始终使用同一密码。</span>
          </template>
        </el-alert>

        <el-button type="primary" size="large" class="setup-button" :loading="loading" @click="handleSubmit">
          {{ loading ? '保存中…' : '保存并进入后台' }}
        </el-button>
      </el-form>

      <p class="setup-footer">{{ version }} · 密码仅保存在本地数据卷中</p>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { User, Lock, CircleCheckFilled } from '@element-plus/icons-vue'
import { useUserStore } from '../stores/user'
import { getAdminInfo, changePassword } from '../api/douyin'
import { APP_VERSION } from '../config'

const router = useRouter()
const userStore = useUserStore()
const version = APP_VERSION

const formRef = ref(null)
const loading = ref(false)
const advancedOpen = ref([])
const originalUsername = ref('admin')

const form = reactive({
  username: 'admin',
  oldPassword: '',
  newPassword: '',
  confirmPassword: ''
})

const rules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 2, max: 20, message: '长度需在 2-20 个字符之间', trigger: 'blur' }
  ],
  newPassword: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 8, message: '新密码长度至少 8 位', trigger: 'blur' }
  ],
  confirmPassword: [
    { required: true, message: '请再次输入新密码', trigger: 'blur' },
    {
      validator: (rule, value, callback) => {
        if (value !== form.newPassword) callback(new Error('两次输入的新密码不一致'))
        else callback()
      },
      trigger: 'blur'
    }
  ]
}

const strength = computed(() => {
  const p = form.newPassword || ''
  let s = 0
  if (p.length >= 8) s++
  if (p.length >= 12) s++
  if (/[a-zA-Z]/.test(p) && /\d/.test(p)) s++
  if (/[^a-zA-Z0-9]/.test(p)) s++
  return Math.min(s, 4)
})
const strengthText = computed(() => ['太短', '较弱', '一般', '较强', '很强'][strength.value])

onMounted(async () => {
  try {
    const res = await getAdminInfo()
    if (res.code === 200) {
      originalUsername.value = res.data.username || 'admin'
      form.username = originalUsername.value
      if (!res.data.must_change_password) {
        router.replace('/')
        return
      }
    }
  } catch (e) {
    return
  }
  try {
    form.oldPassword = sessionStorage.getItem('spark_setup_pwd') || ''
  } catch (e) {}
})

const handleSubmit = async () => {
  if (loading.value) return
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    if (!form.oldPassword) {
      advancedOpen.value = ['adv']
      ElMessage.warning('请填写当前密码（一次性初始密码）')
      return
    }
    if (form.newPassword === form.oldPassword) {
      ElMessage.warning('新密码不能与当前密码相同')
      return
    }
    loading.value = true
    try {
      const name = form.username.trim()
      // 改名与改密一次请求原子完成（后端改密后会使 token 失效，分两步会互相打架）
      const res = await changePassword(form.oldPassword, form.newPassword, name)
      if (res.code === 200) {
        if (name !== originalUsername.value) {
          userStore.setUsername(name)
          originalUsername.value = name
        }
        userStore.clearMustChangePassword()
        try {
          sessionStorage.removeItem('spark_setup_pwd')
        } catch (e) {}
        userStore.logout()
        try {
          await ElMessageBox.alert(res.data || '密码修改成功', '设置完成', {
            confirmButtonText: '去登录',
            type: 'success'
          })
        } catch (e) {}
        router.replace('/login')
      }
    } catch (error) {
      // 错误提示由响应拦截器统一处理
    } finally {
      loading.value = false
    }
  })
}
</script>

<style scoped>
.setup-container {
  position: relative;
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 28px 20px;
  overflow: hidden;
  background: var(--bg);
  background-image: var(--bg-accent);
  background-attachment: fixed;
}

.setup-orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(80px);
  pointer-events: none;
}
.setup-orb--a {
  width: 420px;
  height: 420px;
  top: -140px;
  right: -120px;
  background: color-mix(in srgb, var(--primary) 40%, transparent);
  opacity: 0.45;
}
.setup-orb--b {
  width: 300px;
  height: 300px;
  bottom: -120px;
  left: -80px;
  background: color-mix(in srgb, var(--primary) 24%, #7c5cff 76%);
  opacity: 0.3;
}

.setup-card {
  position: relative;
  z-index: 1;
  width: 100%;
  max-width: 460px;
  padding: 32px 32px 20px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-md);
  animation: fadeInUp 0.32s var(--ease) both;
}

.setup-head {
  text-align: center;
  margin-bottom: 22px;
}

.setup-badge {
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
  box-shadow: 0 10px 24px color-mix(in srgb, var(--primary) 30%, transparent);
}

.setup-title {
  font-size: 19px;
  font-weight: 600;
  color: var(--text-1);
}

.setup-sub {
  margin-top: 6px;
  font-size: 12.5px;
  line-height: 1.6;
  color: var(--text-3);
}

.setup-form :deep(.el-form-item__label) {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-1);
  padding-bottom: 4px;
}

.setup-form :deep(.el-input__wrapper) {
  border-radius: var(--radius-md);
  background: var(--surface-muted);
  box-shadow: none;
  padding: 3px 12px;
  transition: background-color var(--dur) ease, box-shadow var(--dur) ease;
}

.setup-form :deep(.el-input__wrapper.is-focus) {
  background: var(--surface);
  box-shadow: 0 0 0 1px var(--primary) inset;
}

.field-tip {
  margin-top: 6px;
  font-size: 11.5px;
  line-height: 1.5;
  color: var(--text-3);
}

.strength {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 8px;
}

.strength-bar {
  flex: 1;
  height: 4px;
  border-radius: 2px;
  background: var(--surface-muted);
  transition: background-color var(--dur) ease;
}

.strength-bar.active.level-1 { background: #e5484d; }
.strength-bar.active.level-2 { background: #f5a524; }
.strength-bar.active.level-3 { background: #30a46c; }
.strength-bar.active.level-4 { background: var(--primary); }

.strength-text {
  min-width: 34px;
  font-size: 11.5px;
  color: var(--text-3);
  text-align: right;
}

.advanced {
  border-top: none;
  margin-bottom: 12px;
}

.advanced :deep(.el-collapse-item__header),
.advanced :deep(.el-collapse-item__wrap) {
  background: transparent;
  border: none;
}

.advanced-title {
  font-size: 12.5px;
  color: var(--text-3);
}

.setup-alert {
  margin-bottom: 16px;
  border-radius: var(--radius-md);
  background: color-mix(in srgb, var(--primary) 7%, var(--surface-muted));
  border: 1px dashed color-mix(in srgb, var(--primary) 26%, var(--border));
}

:deep(.setup-alert .el-alert__title) {
  color: var(--text-3);
}

.alert-text {
  font-size: 12px;
  line-height: 1.6;
}

.setup-button {
  width: 100%;
  height: 44px;
  font-size: 15px;
  font-weight: 600;
  border-radius: var(--radius-md);
  background: var(--gradient);
  border: none;
  box-shadow: 0 8px 20px color-mix(in srgb, var(--primary) 26%, transparent);
}

.setup-button:hover {
  transform: translateY(-1px);
}

.setup-footer {
  margin-top: 16px;
  text-align: center;
  font-size: 11.5px;
  color: var(--text-faint);
}

@media (max-width: 480px) {
  .setup-card {
    padding: 26px 20px 16px;
  }
}
</style>
