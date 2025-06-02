inter_op_v2 branch without considering voltage variation
inter_op_v3 branch considering voltage vatiation
inter_op_v3 before every run, y, self.voltage_init, self.best_x, self.scheduler.reactor_minutes, self.V_variation, self.scheduler.running_reactors must be set.
self.flag2 = 0 代表完整进行一次波动生产
self.flag2 = 1 代表波动生产中断过