/**
 * 根据环境变量 TZ 判断时区并格式化时间
 * @param dateStr ISO 8601 格式的时间字符串
 * @returns 格式化后的时间字符串
 */
export function formatTimeWithTimezone(dateStr: string): string {
  // 获取环境变量中的时区设置，默认为 'Asia/Shanghai'
  const timezone = process.env.TZ || 'Asia/Shanghai';
  
  const date = new Date(dateStr);
  
  // 使用 toLocaleString 方法将时间转换为指定时区
  return date.toLocaleString('zh-CN', {
    timeZone: timezone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false
  }).replace(/\//g, '-');
}

/**
 * 将时间转换为 Unix 时间戳（秒）
 * @param date Date 对象或时间字符串
 * @returns Unix 时间戳（秒）
 */
export function toUnixTimestamp(date: Date | string): number {
  const d = typeof date === 'string' ? new Date(date) : date;
  return Math.floor(d.getTime() / 1000);
}

/**
 * 将 Unix 时间戳（秒）转换为 Date 对象
 * @param timestamp Unix 时间戳（秒）
 * @returns Date 对象
 */
export function fromUnixTimestamp(timestamp: number): Date {
  return new Date(timestamp * 1000);
}