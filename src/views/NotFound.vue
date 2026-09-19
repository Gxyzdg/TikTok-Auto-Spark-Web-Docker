<template>
  <div class="notfound">
    <div class="notfound-code">404</div>
    <p class="notfound-tip">抱歉，你访问的页面不存在或已被移除</p>
    <el-button type="primary" size="large" :icon="HomeFilled" @click="goHome">
      返回首页
    </el-button>
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'
import { HomeFilled } from '@element-plus/icons-vue'

const router = useRouter()
const goHome = () => router.push('/home')
</script>

<style scoped>
.notfound {
  min-height: 60vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 18px;
  text-align: center;
}

.notfound-code {
  font-size: 64px;
  font-weight: 700;
  line-height: 1;
  letter-spacing: -0.02em;
  color: var(--primary);
  font-variant-numeric: tabular-nums;
}

.notfound-tip {
  font-size: 13.5px;
  color: var(--text-3);
  margin: 0;
}
</style>
