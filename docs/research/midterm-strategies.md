# A 股与港股 1–6 个月中线策略调研与评估

调研日期：2026-11-03

**方法说明**：本报告由 22-agent 调研 Workflow 产出：8 个维度并行文献调研（横截面异象、行为与情绪、博弈与泡沫、国策与国家力量、事件驱动与利好出尽、质量成长与困境反转、高抛低吸数学基础、从业者框架）→ 逐条对抗核验（引文存在性、效应量转述、发表后衰减三个层面独立复核）→ 3 个落地方案比选。共产出 124 条 findings，0 条被证伪，其中 confirmed 100 条、weakened 20 条、unverifiable 4 条；weakened/unverifiable 按降权规则处理——只作线索或注记，不作独立判据。每条证据给出 IEEE 引文、关键效应量、样本期/市场与发表后衰减情况。

**免责声明**：仅供学习研究，不构成投资建议。

## 第 1 章 摘要与结论地图

A 股 1–6 个月的可证据化收益来源不在「强者恒强」，而在质量与预期修正；主要风险不在「涨得慢」，而在追高与拥挤。六条证据主线：①质量与盈利能力是 A 股多重检验后存活最多的会计信号族；②预期修正（EPS 上修、预告超预期）是该期限最强的正向漂移；③A 股月度反转强、经典动量缺失，追高是负期望，「反转规避」本身即是 alpha；④政策支持须四级分层——L1 顶层规划只是候选池，L3 资金落地 + L4 业绩兑现才支撑 6 个月持有；⑤「利好出尽」是一族机制相反的效应，量化硬消息倾向漂移、叙事软消息倾向回吐；⑥高抛低吸的数学确定性部分仅年化约 1–3 个百分点（excess growth rate），必须 regime 门控。折价纪律贯穿全文：文献效应量按样本外约 7 折设定预期、CH-4 风险调整后再折；weakened/unverifiable 条目只作注记；新策略置信帽 0.65、后验样本 <30 只观察不记分。方案比选结论：以方案 A「策略即数据 + profile 双轨」为骨架，嫁接方案 C 的规约 SSOT 与拒绝清单、方案 B 的分阶段切分。

## 第 2 章 A 股横截面证据基线与多重检验纪律

A 股横截面结构与美股系统性不同：价值用 EP 度量优于 BM，小盘受壳价值污染须剔最小 30%，换手类情绪信号最强，单一因子在多重检验后几乎全军覆没——这决定了后续所有策略都必须以多条件合流而非单因子形态落地。

基准模型：CH-3/CH-4 以 EP 为价值度量、规模因子剔除最小 30%，SMB 月均 1.03%、VMG 月均 1.14%（t=3.25/4.34），EP 在 Fama-MacBeth 回归中淹没 BM/AM/CP（t=4.38 vs 其余 <1.4）；样本 A 股 2000–2016；发表后成为 A 股实证标准基准，被后续系列广泛引用且样本外仍成立（J. Liu, R. F. Stambaugh, and Y. Yuan, "Size and value in China," *Journal of Financial Economics*, vol. 134, no. 1, pp. 48-69, 2019）。

反转强、动量缺：A 股 1 月反转 CAPM alpha 18%/年（t=2.96），经典 12-1 动量全样本仅 0.198%/月（t=0.71 不显著）；仅高价股（散户参与少）第 10 价格分位组动量达 1.643%/月（t=3.73）——动量存在与否是投资者结构的状态变量。大票 Universe 中等权 1 月反转 1.52%/月（t=3.36）vs 动量 0.37%/月（t=0.76）（样本 2008–2020）（J. Du, D. Huang, Y.-J. Liu, Y. Shi, A. Subrahmanyam, and H. Zhang, "Nominal Prices, Retail Investor Participation, and Return Momentum," *Management Science*, vol. 72, no. 3, pp. 2064-2089, 2026（2025 epub ahead of print）；M. Jansen, L. Swinkels, and W. Zhou, "More powerful tests for anomalies in the China A-share market," *Journal of Portfolio Management*, vol. 50, no. 4, pp. 186-202, 2024）。

多重检验纪律基线：HQZ 在 t≥2.85 门槛下检验 454 个 A 股单变量策略，VW 原始收益仅 8% 存活、CH-4 调整后 0% 存活（美国对应 18%/1%）；少数幸存者中 SUE1 等权 1.13%/月（t=7.02）、CH-4 α 0.68%/月（t=3.79）最为突出，季节性（同月历史收益 Ra25）0.76%/月（t=2.93）是唯一存活的过去收益类信号——但同月收益需 ≥3 年月度数据，当前 BARS_WINDOW=250 不可精确计算。ML 实证同向确认：A 股月度 OOS R² 最高约 2.58%（美国 0.40%），流动性/换手类特征重要性第一（K. Hou, F. Qiao, and X. Zhang, "Finding anomalies in China," SSRN Working Paper No. 4322815, 2023；M. Leippold, Q. Wang, and W. Zhou, "Machine learning in the Chinese stock market," *Journal of Financial Economics*, vol. 145, no. 2, pp. 64-82, 2022）。

两条已削弱但仍常用的信号须降档使用：52 周高点锚定 6–12 个月持有期 raw 收益 0.71–0.78%/月（t=2.15–2.31），但 HQZ 中 CH-4 α 不显著（0.78，t=1.64），且 Liu-Liu-Ma 明确多数市场计入交易成本后利润不再显著（M. Liu, Q. Liu, and T. Ma, "The 52-week high momentum strategy in international stock markets," *Journal of International Money and Finance*, vol. 30, no. 1, pp. 180-204, 2011；核验：weakened——只作组合条件与信息面读出，不作独立买点）；盈利能力族（roe1 1.26%/月 t=3.73、droa1 0.97%/月 t=4.56）方向成立，但转引的 A 股质量研究刊名有误，且 LSY 证明 EP 价值因子可吸收 ROE 异象（CH-3 α −0.36% 不显著）——质量与价值在 A 股高度纠缠（核验：weakened——按盈利能力单支柱使用）。低波动 VOL 因子年化 9.1%、Sharpe 0.88（A 股 2000–2018，剔最小 30%），与 LSY「CH-3 已解释波动率异象」的冲突源于回看窗口口径（36 个月 vs 1 个月），引用须注明（D. Blitz, M. X. Hanauer, and P. van Vliet, "The volatility effect in China," *Journal of Asset Management*, vol. 22, 2021）。

## 第 3 章 质量与成长持续性：均值回复是主旋律

质量的正确用法是「下行过滤器 + 预期差定位器」，不是独立 alpha 引擎；高增长不可线性外推，单期高 ROE 必须按均值回复校准。

盈利向均值回复的速度快且非线性：ROE 年约 38% 回复均值，低位与远离均值时回复更快；样本美国 1964–1996；已成为 q-factor/FF5 的标准假设（E. F. Fama and K. R. French, "Forecasting Profitability and Earnings," *The Journal of Business*, vol. 73, no. 2, pp. 161-175, Apr. 2000）。成长几乎不持续：经营收益连续 5 年跑赢中位数的公司占 3.6%，与纯随机的 3.125% 无实质差异，卖方长期增长预测系统性乐观且无预测力；2023 年复制（1997–2022）模式不变（L. K. C. Chan, J. Karceski, and J. Lakonishok, "The Level and Persistence of Growth Rates," *The Journal of Finance*, vol. 58, no. 2, pp. 643-684, Apr. 2003）。落地含义：ROE/ROIC 按「近 4 期均值 + 稳定性（1−极差/均值）」打分，增速 >50% 的标的默认按两年衰减预期折价而非给估值溢价。

盈利能力是独立于价值的定价维度：GP/A 多空 FF3 alpha 约 0.52%/月（t=4.49），与价值组合叠加时增强最显著——「便宜 + 能赚钱」是跨期限通用的核心正信号（R. G. Novy-Marx, "The Other Side of Value: The Gross Profitability Premium," *Journal of Financial Economics*, vol. 108, no. 1, pp. 1-28, Apr. 2013）。价值陷阱可事前识别：估值与基本面强度「错配」的标的贡献全部价值-成长价差，匹配组价差为零（J. D. Piotroski and E. C. So, "Identifying Expectation Errors in Value/Glamour Strategies," *The Review of Financial Studies*, vol. 25, no. 9, pp. 2841-2875, Sep. 2012）。F-score 原版高 BM 股年收益提升至少 7%、多空年化 23%（美国 1976–1996），但 A 股分布与美股相反——溢价集中在低 BM 样本（月均 1.28%）而非高 BM 侧，照搬美式高 BM 抄底用法会选错样本（J. D. Piotroski, "Value Investing: The Use of Historical Financial Statement Information to Separate Winners from Losers," *Journal of Accounting Research*, vol. 38, Supplement, pp. 1-41, 2000；A 股侧证据为学位论文层级，降档引用）。

## 第 4 章 困境反转、壳价值与退市制度：翻身必须绑定催化

「困境反转」在两个市场都是负基数选择：美股高困境风险股低收益 + 高波动，A 股小盘困境股的壳价值红利已被注册制与退市新规制度性拆除——无催化的深跌低位股是负期望。

困境风险是负选择而非被补偿的风险：按前瞻违约概率排序，收益几乎随风险单调递减，高困境组低收益 + 高 σ + 高 β（美国 1963–2003）（J. Y. Campbell, J. Hilscher, and J. Szilagyi, "In Search of Distress Risk," *The Journal of Finance*, vol. 63, no. 6, pp. 2899-2939, Dec. 2008）。A 股侧的机制是壳价值：最小 30% 市值公司约 30% 市值为借壳期权价值，收益与基本面脱钩；注册制（2019/2020/2023）+ 2024 新国九条退市收紧（主板市值线 3→5 亿元、2024 年退市 52 家创纪录）使壳价值制度性坍缩，2017 年前「小盘困境博翻身」的历史数据不可外推（C. M. C. Lee, Y. Qu, and T. Shen, "Reverse mergers, shell value, and regulation risk in Chinese equity markets," Stanford GSB Working Paper No. 3604, 2017）。

长期反转提供超跌维度的理论锚：3 年输家随后 36 个月跑赢赢家约 24.6%（t=2.20，美国 1926–1982），A 股方向成立但证据层级较低（W. F. M. De Bondt and R. Thaler, "Does the Stock Market Overreact?" *The Journal of Finance*, vol. 40, no. 3, pp. 793-805, 1985）。财务困境预警可用负债率分位 + 连续亏损期数 + ST 标注三档替代（Z-China 模型提前 2–3 年预测 ST 准确率约 80%；Z. Zhang, E. I. Altman, and J. Yen, "Corporate financial distress diagnosis model and application in credit rating for listing firms in China," *Frontiers of Computer Science*, vol. 4, no. 2, pp. 220-236, 2010）。周期股的「高 PE 买、低 PE 卖」有正式理论支撑：competition neglect + 需求外推使高景气→高投资→低回报可预测（R. Greenwood and S. G. Hanson, "Waves in Ship Prices and Investment," *The Quarterly Journal of Economics*, vol. 130, no. 1, pp. 55-109, Feb. 2015；Lynch 六类公司分类作分类闸门，practitioner 档）。落地为 turnaround_catalyst 策略：ST/市值 <30 亿锁死翻身置信上限，深跌 + 困境度非高危 + 可验证催化（预告扭亏/盈喜/摘帽公告）三者齐备才给分。

## 第 5 章 换手、注意力与涨停：A 股中期情绪的可计算指纹

换手率是 A 股最强的中期情绪信号，且注意力事件（涨停、上新闻、极端单日涨跌）后的追涨在 1–6 个月维度系统性负期望；个股级换手/涨停计数全部可由现有 daily_bars 本地推导，无需新增取数。

换手定价：CH-4 的 PMO 因子（做多低异常换手/做空高异常换手）年均约 12%，异常换手 CAPM alpha 1.28%/月（t=2.86）；换手与反转互相解释——加入 PMO 后反转 alpha 减半，二者不可双计。注意力驱动买入：极端单日涨跌股的买入-卖出失衡约 +24%/+29%，注意力对买入侧的影响远大于卖出侧（美国 7.8 万账户 1991–1996，引用 7600+）（B. M. Barber and T. Odean, "All That Glitters: The Effect of Attention and News on the Buying Behavior of Individual and Institutional Investors," *Review of Financial Studies*, vol. 21, no. 2, pp. 785-818, 2008）。涨停是 A 股制度化的注意力事件：上海 645 万账户 2442 个涨停事件显示 t+1 散户净买入、t+1→t+6 显著均值回归（M. S. Seasholes and G. Wu, "Predictable behavior, profits, and attention," *Journal of Empirical Finance*, vol. 14, no. 5, pp. 590-610, 2007）；大户在涨停日买入次日卖出，其净买入越强长期反转越强，ST 股 5% 涨跌幅下破坏性行为更强（T. Chen, Z. Gao, J. He, W. Jiang, and W. Xiong, "Daily price limits and destructive market behavior," *Journal of Econometrics*, vol. 208, no. 1, pp. 249-264, 2019）。

账户级结构证据：<10 万元小散户买入未来输家、>50 万元大散户方向正确（上交所 2016–2019）；2014–15 泡沫期外推信念×处置效应使成交量额外 +30%、总量达泡沫前 4 倍（C. M. Jones, D. Shi, X. Zhang, and X. Zhang, "Retail Trading and Return Predictability in China," *Journal of Financial and Quantitative Analysis*, vol. 60, no. 1, pp. 68-104, 2025；J. Liao, C. Peng, and N. Zhu, "Extrapolative bubbles and trading volume," *Review of Financial Studies*, vol. 35, no. 4, pp. 1682-1722, Apr. 2022）。两条情绪信号降档：CGO（资本利得悬挂）在中国的定价符号未经公开摘要证实（M. Kong, M. Bai, and P. Wang, "Is disposition related to momentum in Chinese market?" *Managerial Finance*, vol. 41, no. 6, pp. 600-614, 2015；核验：weakened——只作线索，禁止直接移植美股低 CGO 因子方向）；MAX（近月最大单日涨幅）负向预测 raw 口径成立（EW −1.08%/月 t=−4.12），但「3–6 个月持有期仍显著」依赖无法核实的数字（核验：weakened——只作降档闸）。可操作判据：异常换手（近 20 日均换手/近 250 日均换手）>1.5 且换手 250 日分位 >80% → buy 降档；换手分位 >95% 且价格 20 日不创新高 → 顶部形态；近 20 日涨停计数 ≥2 → 禁 strong_buy 晋级。

## 第 6 章 事件与利好出尽：一族机制相反的效应

「利好出尽」不是一个效应而是一族：欠反应型（PEAD、修正动量）公告后沿消息方向漂移，是方向票候选；过度反应/抢跑型（软叙事、指数纳入、高送转、政策兑现日）公告后回吐，是风险降档候选。判据核心是「公告前累计超额 × 兑现日量价形态 × 消息可量化程度」三元组。

隔夜/日内拆分是 A 股独有的零成本信号：盈余公告反应几乎全部发生在隔夜，日内反向交易隔夜方向；公告日隔夜跳空 >+3% 且日内回吐过半 → 机器可读的兑现抛压，直接 downgrade（J. Liu, O.-K. Hope, and D. Hu, "Earnings announcements in China: Overnight-intraday disparity," *Journal of Corporate Finance*, vol. 82, art. 102471, 2023）。抢跑-兑现：52 周赢家股公告前显著正超额、公告后显著负超额（D. Aboody, R. Lehavy, and B. Trueman, "Limited Attention and the Earnings Announcement Returns of Past Stock Market Winners," *Review of Accounting Studies*, vol. 15, no. 2, pp. 317-344, 2010）；大样本新闻定价研究显示叙事性软新闻公告日冲高后 20 日净回吐约三分之二（day-0 位移是 day+20 的 2.8 倍），量化基本面新闻则持续漂移（A. Kargarzadeh et al., "Buy the Rumor, Sell the News: When Is News Priced In?" arXiv:2608.14014, 2026——预印本降档引用）。A/HK 公告日历溢价不显著：46 国样本中中国与香港点估计 t≈1，「持券等公告」在两市平均无收益（核验：weakened——原引文出处有误，正确出处为 *Journal of Financial Economics*, vol. 108, no. 1, pp. 118-138, 2013；结论本身按负向设计规则使用：披露日临近只触发风险检查，不作 buy 理由）。

A 股特有制度件：解禁 CAR(−120,+20) 约 −14%，比例越大跌幅越大，属最稳的事件负效应之一（L. Liao, B. Liu, and H. Wang, "Information Discovery in Share Lockups: Evidence from the Split-Share Structure Reform in China," *Financial Management*, vol. 40, no. 4, pp. 1001-1027, 2011）；高送转是制度化「炒预期-除权回落」，疑似操纵性送转先涨后跌破送转前水平，高送转 × 同期减持/解禁并发是交易所指引点名的操纵形态（S. Titman, C. Wei, and B. Zhao, "Corporate actions and the manipulation of retail investors in China," *Journal of Financial Economics*, vol. 145, no. 3, pp. 762-787, 2022）。正向侧：分析师预期修正是 3–6 个月稳健漂移（美国 1973–1993 原始证据 + A 股卖方验证：上调后 60 日超额约 4.0%，但公告前 20 日涨幅已 >+20% 时显著变弱——修正被抢跑侵蚀，核验：events-02 转述曾低估 A 股 PEAD 的期限与量级，按原文摘要口径应为公告后最长 1 年漂移、对冲超额约 9.5%，采用修正后口径；H. C. Truong, "Post-earnings announcement abnormal return in the Chinese equity market," *Journal of International Financial Markets, Institutions and Money*, vol. 21, no. 5, pp. 637-661, 2011）（L. K. C. Chan, N. Jegadeesh, and J. Lakonishok, "Momentum Strategies," *Journal of Finance*, vol. 51, no. 5, pp. 1681-1713, 1996）。回购公告须条件化：公告前价量已高的样本反应显著更弱，「市值管理/股权激励」目的回购已无平均超额（X. Wu, H. G. Kang, and D. Ryu, "Pre-announcement trading states and share repurchase announcement returns," SSRN WP no. 7557183, 2026；D. Li and R. Zou, "Herd to repurchase," *Pacific-Basin Finance Journal*, vol. 92, art. 102782, 2025）；指数纳入公告前 150 日涨幅越高公告后越差（C. Wang, Z. Murgolov, and J. Haman, "Impact of changes in the CSI 300 Index constituents," *Emerging Markets Review*, vol. 24, pp. 13-33, 2015——核验修正卷期；核验：weakened——减持样本数字为单一 practitioner 源，只作规避追高提示，不作机械信号）。

## 第 7 章 国策支持与国家力量：政策四级分层

A 股是证据意义上的政策驱动市场，但「政策利好」的正向证据集中在事件窗与公司级落地，顶层规划本身的方向是「先涨后兑现失败」。可操作框架是四级分层：L1 顶层规划只给主题候选资格，L2 部委细则启动 1–2 个月事件窗，L3 资金落地 + L4 业绩兑现才有 6 个月持有资格。

定价核心是政策会议而非宏观数据：2009–2022 年 95 次顶层会议前 48 小时平均 +42bp（高波动组 +91bp），会后收益小且不显著，M2/CPI 公告前无此效应——「涨在会前不在会后」，会前已涨满的仓位落地日按利好出尽评估（J. Pan and Q. Peng, "Top Government Meetings in China," Working Paper, SAIF SJTU, Mar. 2025）。产业政策「先涨后兑现失败」有严格实证：中国制造 2025 发布后目标行业公告期超额 +4.5%、短期 CAR +9.9%（不同事件窗口径），但 2015–2018 大幅跑输、补贴未实际落地、ROA/ROE 反而下滑（X. Liu, W. L. Megginson, and J. Xia, "Industrial policy and asset prices," *Journal of Banking & Finance*, vol. 142, 106554, 2022）；五年规划支持行业五年 BHAR 更高，但效应随国有股权占比上升单调减弱（D. Chen, O. Z. Li, and F. Xin, "Five-year plans, China finance and their consequences," *China Journal of Accounting Research*, vol. 10, no. 3, pp. 189-230, Sep. 2017）。

国家力量的真实形态：2015 救市创造价值净额约 +2060 亿元但只在系统性危机窗口可信（Y. Huang, J. Miao, and P. Wang, "Saving China's Stock Market?," *IMF Economic Review*, vol. 67, no. 2, pp. 349-394, Jun. 2019）；常态化代价是价格信息含量下降——国家队持股使波动率平均 −3.45%，但盈余反应钝化、知情交易者年化 20.6% vs 对照 13.8%（T. V. Dang, W. Li, and Y. Wang, "Government Stock Purchase Undermines Price Informativeness: Evidence from China's National Team," *Journal of Financial and Quantitative Analysis*, vol. 59, no. 5, pp. 2340-2374, Aug. 2024）；2023-10 起汇金 ETF 买入已制度化为类平准基金（2025 年末持仓约 1.53 万亿元；中国证券报/山西证监局, 2025-2026，official/media 档），只作系统性急跌情景的权重下调，不作个股买点。负向冲击不可对冲：双减单日 −54%~−70%、一周蒸发约 1000 亿美元（CNBC/Al Jazeera, Jul. 2021，交易所行情数字，media 档）——政策尾部风险只能事前敞口管理（监管敏感行业清单 + 征求意见稿/官媒点名即 veto），不能靠止损（跌停来不及）。春季躁动是 A 股最强政策-季节复合效应：2 月胜率 76%（2004–2024 万得全 A），行情大概率终结于 3 月两会与 4 月政治局会议之间（陈刚、陈李等, "岁末年初有哪些季节性效应？" 东吴证券策略周评, 2024-12-22——practitioner 统计，多券商口径一致）；「反内卷」类价格治理行情按 4–8 周衰减窗口处理，无商品价格/减产验证则了结（Global Times/Reuters, Jul.–Aug. 2025——media 档降权）。

## 第 8 章 港股结构差异与南向资金

港股不是「另一个 A 股」：机构约 56% 成交（海外机构 36%）、零售仅 15%，A 股式散户情绪信号弱一个数量级；南向资金（T-1 披露）是最可得的大陆情绪通道，但其预测力对频率与口径高度敏感。

结构常数：HKEX Cash Market Transaction Survey 2020；南向占主板 ADT 14.7%（2023H1），2014 年 9 亿港元增至 338 亿。横截面：香港是少数「价值可用、动量看期间」的市场——β 不定价，size/BM/EP 捕获横截面变异（K. S. Lam, "The relationship between size, book-to-market equity ratio, earnings-price ratio, and return for the Hong Kong stock market," *Global Finance Journal*——核验：weakened，卷期页修正为 vol. 13, no. 2, pp. 163-179, 2002）；六个亚太市场动量几乎不显著（A. Hameed and Y. Kusnadi, "Momentum strategies: Evidence from Pacific Basin stock markets," *Journal of Financial Research*, vol. 25, no. 3, pp. 383-397, 2002）。南向资金：持股比例变化周频正向预测港股收益（FF5 调整后年化最高 25.84%，2025 刊出，样本内数字、实盘含成本大幅缩水），但 Bian et al. 发现净买入仅在日频显著、周频不显著——口径冲突未决，只作情报面佐证不作主信号（T. Ding, W. Song, J. Bian, and G. Zhang, "Southbound capital flows and stock return predictability," *Pacific-Basin Finance Journal*, vol. 93, 102887, Oct. 2025）。AH 溢价是分离两地定价的结构变量：149 对 A+H 滞后溢价负向预测 A 股收益（系数 −2.454，t=−6.09）、正向预测 H 股收益，收敛主要由 A 股端完成；押 AH 收敛的套利者长期大亏，只作 A 股端风险提示（J. N. Carpenter, R. F. Whitelaw, and D. Zou, "Information in the A-H Premium," Working Paper, NYU Stern / Indiana University, Feb. 2026）。落地：港股中期情绪降级为「南向持股比变化 + 量能」代理，moneyflow 块已有南向持股（T-1），力度弱一档并显式注记。

## 第 9 章 博弈论、泡沫与 AI 主题

泡沫不可预测但可识别状态：聪明钱选择骑泡沫而非刺破（同步化问题），两年翻倍后的崩盘概率与判别特征都有可计算锚；2026 年 A 股 AI 泡沫的破裂几乎逐项命中文献特征清单，是上述机制的活体样本。

同步化问题解释「利好出尽」的博弈内核：即使所有人都知道泡沫存在，无法协调卖出使其持续超预期，而新闻事件可充当协调装置——信息含量很小也能引发不成比例的下跌（D. Abreu and M. K. Brunnermeier, "Bubbles and crashes," *Econometrica*, vol. 71, no. 1, pp. 173-204, Jan. 2003）。核心实证锚：行业两年净超额涨幅 >100% 后，两年内 40% 级回撤概率从无条件 14% 升至 53%（150% 时 80%），加速度、波动率抬升、新发行、年轻公司领涨显著区分崩与不崩，换手率水平无判别力；识别点后到顶点平均仍有约 30% 上行（美国 FF-49 行业 1926–2014，40 起 ≥100% 事件 21 起崩盘）（R. Greenwood, A. Shleifer, and Y. You, "Bubbles for Fama," *Journal of Financial Economics*, vol. 131, no. 1, pp. 20-43, 2019）。两条择时转述须修正：「识别后持有、回撤 10% 离场」的 trailing stop 规则在 GSY 原文不存在（Table 8 全部为信号触发即卖）——10% 回撤离场作为工程纪律保留但不引为文献结论（核验：weakened）；对冲基金骑泡沫的「崩盘期间 −0.3%/月」数字全文不存在，保留「技能在退出节奏不在识别」（核验：weakened）（M. K. Brunnermeier and S. Nagel, "Hedge funds and the technology bubble," *Journal of Finance*, vol. 59, no. 5, pp. 2013-2040, Oct. 2004）。

供给侧热度顶信号：主题 ETF 在热度顶发行，底层股票上市后 5 年风险调整跑输约 30%（约 −6%/年）（I. Ben-David, F. Franzoni, B. Kim, and R. Moussawi, "Competition for attention in the ETF space," *Review of Financial Studies*, vol. 36, no. 3, pp. 987-1042, Mar. 2023）。A 股转售期权证据：A 对 B 股平均溢价 420%、换手解释截面溢价约 20%；2005–08 年 18 只必归零认沽权证仍被日均换手近 3 次地交易——流通筹码少 + 换手高即转售期权定价区（核验：weakened——主体数字经 NBER 原文核实，一处归属需更正）（J. Mei, J. A. Scheinkman, and W. Xiong, "Speculative trading and stock prices," *Annals of Economics and Finance*, vol. 10, no. 2, pp. 225-255, 2009；W. Xiong and J. Yu, "The Chinese warrants bubble," *American Economic Review*, vol. 101, no. 6, pp. 2723-2753, 2011）。蹭热点定价链：改名 .com 十日 CAR 约 +74%，机会主义蹭热点公司存在显著长期反转——题材真伪比题材多少更决定反转（M. J. Cooper, O. Dimitrov, and P. R. Rau, "A Rose.com by any other name," *Journal of Finance*, vol. 56, no. 6, pp. 2371-2388, 2001）。TMT 成交占比 40% 法则未经一手文本确认且 2025 年自认失效（MSCI, "Integrated Factor Crowding Model," MSCI Research Model Description, 2019/2023；广发证券策略研究, 2025-02——practitioner 档；核验：unverifiable——只作 news 注记并强制注明「阈值非结构常数」）。数学侧：PSY GSADF 广义 sup ADF 检验可对日收盘序列实时 date-stamp 爆炸性过程（P. C. B. Phillips, S. Shi, and J. Yu, "Testing for multiple bubbles: Historical episodes of exuberance and collapse in the S&P 500," *International Economic Review*, vol. 56, no. 4, pp. 1043-1078, 2015），属新增确定性判据、须走门禁评审。2026 现场印证：科创50 自 6/7 月高点回撤约 40%、PE(TTM) 从约 250 倍回落至约 100 倍，两融余额自峰值 3.033 万亿降至 2.41 万亿——量能、加速度、杠杆三特征齐现。

## 第 10 章 高抛低吸的数学基础：再平衡、带宽、止损与仓位

高抛低吸唯一无需预测能力的收益来源是 stochastic portfolio theory 的 excess growth rate，量级仅年化 1–3 个百分点；它在趋势发散市等价于做空跨式，必须配 regime 开关。这一章的结论把「波段」从风格选择变成数学约束。

γ* = ½(Σwᵢσᵢ² − σ_p²) 是协方差结构的恒等式：单票 + 现金各半、年化 σ=40% 时理论上限约 2%/年（未扣成本）（R. Fernholz and B. Shay, "Stochastic portfolio theory and stock market equilibrium," *The Journal of Finance*, vol. 37, no. 2, pp. 593-603, 1982）。实证侧 diversification return 存在但有限：等权再平衡组合的超额约一半来自分散、一半来自再平衡本身（D. G. Booth and E. F. Fama, "Diversification returns and asset contributions," *Financial Analysts Journal*, vol. 48, no. 3, pp. 26-32, 1992）。条件性是最强的反对面：趋势发散市中再平衡等价于买入持有 + 做空相对价值跨式（负凸性），扣成本后多数参数化再平衡策略期望增值 ≈ 0 或为负（W. G. Hallerbach, "Disentangling rebalancing return," *Journal of Asset Management*, vol. 15, no. 5, pp. 301-316, 2014；K. Cuthbertson, S. Hayley, N. Motson, and D. Nitzsche, "What does rebalancing really achieve?" *International Journal of Finance & Economics*, vol. 21, no. 3, pp. 224-240, 2016；N. Granger et al., "Rebalancing risk," SSRN WP 2488552, 2014）。网格在随机游走下期望 = −成本 × 交易数（净负），只能作「已确认均值回复 regime 下的带宽化执行器」。均值回复的可计算检验是方差比：A 股个股偏 VR<1 且月度反转强，比美股更适合 1 个月尺度低吸高抛（A. W. Lo and A. C. MacKinlay, "Stock market prices do not follow random walks," *Review of Financial Studies*, vol. 1, no. 1, pp. 41-66, 1988）；关闭判据是 TSMOM：过去 12 个月自身收益为正的资产未来 1–12 个月延续，跨 58 个市场成立且极端行情中最好——强 TSMOM 段止盈与再平衡都是负期望动作（T. J. Moskowitz, Y. H. Ooi, and L. H. Pedersen, "Time series momentum," *Journal of Financial Economics*, vol. 104, no. 2, pp. 228-250, 2012）。

止损的数学是反直觉的：GBM 下止损不改善期望收益（同比例降波动降收益），动量过程下有益、均值回复过程下有害——A 股 VR<1 个股上的贴价紧止损会系统性卖在阶段低点，下行保护应来自带宽与总回撤硬门（K. M. Kaminski and A. W. Lo, "When do stop-loss rules stop losses?" *Journal of Financial Markets*, vol. 19, pp. 214-224, 2014）。仓位：半 Kelly 保留约 3/4 增长率、方差减半；1/N 在 14 组实验中样本外 Sharpe 不低于均值方差优化——「波动倒数加权 + 硬性单票上限」优于精确优化（L. C. MacLean, E. O. Thorp, and W. T. Ziemba, "Good and bad properties of the Kelly criterion," *Quantitative Finance*, vol. 10, no. 7, pp. 681-687, 2010；V. DeMiguel, L. Garlappi, and R. Uppal, "Optimal versus naive diversification: How inefficient is the 1/N portfolio strategy?" *Review of Financial Studies*, vol. 22, no. 5, pp. 1915-1953, 2009）。波动率目标作风险管理有效但样本外不总是赢（A. Moreira and T. Muir, "Volatility-managed portfolios," *The Journal of Finance*, vol. 72, no. 4, pp. 1611-1644, 2017；S. Cederburg, M. S. O'Doherty, F. Wang, and Y. S. Yan, "On the performance of volatility-managed portfolios," *Journal of Financial Economics*, vol. 138, no. 1, pp. 95-117, 2020；核验：weakened——引文按核验修正：Moreira & Muir 页码为 pp. 1611-1644（非 1617-1651）、Cederburg et al. 真实标题与卷页为 JFE 138(1):95-117（finding 原引标题与卷页均有误）；二者反证并读，只降仓位不提信号）。最小带宽 g ≥ max(2σ_d×√21, 3×往返成本)——σ_d 为日已实现波动、√21 折算月窗（2σ_d×√21 即月收益 2 倍标准差）：A 股典型 σ_d≈1%–2% → g≈9%–18%，港股 σ_d≈1.5%–2.5% → g≈14%–23%；成本下限（3× 往返成本，按成本常量上限口径 A 股约 0.45%、港股约 1.05%）仅在极低波动票上生效（核验：weakened——费率官方原文未复核，成本常量表须带生效日期并在落地前重验）。长期分布的极端偏度支持核心-卫星：1926–2016 美股仅约 4% 个股创造全部净财富，卫星仓硬帽 ≤30%（H. Bessembinder, "Do stocks outperform Treasury bills?" *Journal of Financial Economics*, vol. 127, no. 2, pp. 248-264, 2018）。

## 第 11 章 行为交易损耗与拉长周期的结构性收益

把操作周期从「频繁」拉长到 1–6 个月本身就是证据支持的结构性收益：高换手散户的亏损在美、台、中三个市场一致复制，泡沫期的财富再分配由主动交易的时机差驱动。

最活跃 20% 散户组年净收益 11.4% vs 市场 17.9%（美国 66,465 户，1991–1996），「过度交易有害」是行为金融复制最稳的结果之一（B. M. Barber and T. Odean, "Trading is hazardous to your wealth: the common stock investment performance of individual investors," *The Journal of Finance*, vol. 55, no. 2, pp. 773-806, 2000）。2014–15 A 股泡沫-崩盘期间，最大的 0.5% 家庭群体获利、底部 85% 亏损，通过主动交易再分配约 2500 亿元（≈两组各自初始股权财富的 30%），非泡沫期该再分配仅为 1–3%（核验：weakened——原转述 ~1000 亿元低估 2.5 倍，已按原文摘要修正为 2500 亿元；正文采用修正后数字）（L. An, D. Lou, and D. Shi, "Wealth redistribution in bubbles and crashes," *Journal of Monetary Economics*, vol. 126, pp. 134-153, 2022）。新股民是日频动量的驱动者，而周/月频动量不存在——趋势类策略在 A 股的持有语义不应外推到 6–12 个月动量逻辑（Z. Gao, W. Jiang, W. A. Xiong, and W. Xiong, "Daily Momentum and New Investors in Emerging Stock Markets," NBER Working Paper no. 31839, 2023）。落地：信号可日更，建议动作带宽化（swing_band 类信号设 min_holding_days ≥10，同向信号在最小持有窗内不重复触发）。

## 第 12 章 从业者框架降档附录

从业者框架按「能否确定性规则化」分三档使用：完全可代码化的只取其无歧义阈值（Weinstein 四阶段、Minervini 趋势模板）；半规则化的交给 LLM 判读 + 确定性门槛复核（Lynch 六分类、Marks 温度计）；不可规则化的只作 regime 背景。全部按 practitioner 档降权，不与同行评审证据同席。

可代码化子集：Weinstein 的 30 周均线（≈MA150）阶段框架判据最完全可翻译（S. Weinstein, *Secrets for Profiting in Bull and Bear Markets*, Dearborn, 1988）；Minervini SEPA 八条阈值（价 >MA150 >MA200、MA200 上行、距 52 周高点 ≤25% 等）适合直接进策略 YAML，但所有回测数字未核实（M. Minervini, *Trade Like a Stock Market Wizard*, McGraw-Hill, 2013）。关键修正：二者的 RS 动量判据在 A 股必须降权——A 股是个股动量最不显著的市场之一，应改用短期反转与行业口径。Lynch 六类公司分类作诊股先验闸门（周期股用 PB 不用 PE），PEG 可确定性计算且有 EP 因子支撑（P. Lynch and J. Rothchild, *One Up on Wall Street*, Simon & Schuster, 1989）。Marks 温度计规则化：估值分位 >p90 + 60 日涨幅 >40% → 压 strong_buy→buy（核验：weakened——1991 年 memo 题名不符，钟摆框架以 *The Most Important Thing*（Columbia University Press, 2011）与 2023/2025 memo 档案为准）。风险平价只迁移「波动率倒数配权」子集：AFP 2012 证明风险平价 Sharpe 系统性高于 60/40，但须与同期刊对冲证据并读、且不引入杠杆（核验：weakened）（C. Asness, A. Frazzini, and L. H. Pedersen, "Leverage Aversion and Risk Parity," *Financial Analysts Journal*, vol. 68, no. 1, pp. 46-59, 2012）。业绩双锚（已核）：红利低波 ETF 512890 七年 21.57%/9.46%/19.56%/2.72%/11.91%/22.64%/4.74%（累计 +147.68%，至 2026-11-02）与科创50 ETF 588000（2025 +35.72% 但成立以来 −12.16%、2026-10 单月 −21.75%）构成 A 股「质量端 vs 主题端」哑铃两端的真实业绩锚——风格拥挤周期与防御属性均可在逐年数字中直接观察。美林时钟与货币-信用四象限无可核回测（T. Greetham and R. Hartnett, "The Investment Clock: Making Money from Macro," Merrill Lynch Global Research, Nov. 2004——原文 PDF 未核实；核验：unverifiable），拒绝作 regime 信号（见拒绝清单）。

## 第 13 章 证据纪律与折价规则

所有策略准入与置信设定都压在三条元证据上：发表后衰减真实但不归零、复制率对测量选择敏感、A 股单变量异象在多重检验下几乎全灭。落地为五条准入门槛。

元证据：97 个美股预测变量的组合收益样本外降 26%、发表后降 58%（R. D. McLean and J. Pontiff, "Does Academic Research Destroy Stock Return Predictability?" *The Journal of Finance*, vol. 71, no. 1, pp. 5-32, 2016）；但 93 国贝叶斯复制框架给出 82.4% 复制率，多数因子簇样本外仍显著（T. I. Jensen, B. Kelly, and L. H. Pedersen, "Is there a replication crisis in finance?" *Journal of Finance*, vol. 78, no. 5, pp. 2465-2518, 2023）；美国是唯一有可靠发表后衰减的国家，A/HK 套利受限更深、衰减理论上更慢但容量更小（B. Jacobs and S. Müller, "Anomalies across the globe," *JFE*, vol. 138, no. 1, pp. 194-214, 2020）。复制率之争须并读：HXZ 称美股 452 异象 t≥1.96 复制率仅 35%（核验：weakened——数字转述经修正：65% 无法通过 |t|≥1.96；K. Hou, C. Xue, and L. Zhang, "Replicating anomalies," *Review of Financial Studies*, vol. 33, no. 5, pp. 2017-2134, 2020）；A 股侧 469 变量的系统复制显示 83.37% 无显著多空价差（Z. Li, L. X. Liu, X. Liu, and K. C. J. Wei, "Replicating and Digesting Anomalies in the Chinese A-Share Market," *Management Science*, 2024）。

准入门槛（写入策略规约）：①证据分级——中国市场样本 > working_paper > 美股-only（后者降档或拒绝）；②单因子只作组合信号（rank 复合分），不作独立策略；③新策略置信帽 0.65，多条件合流才出非 hold，缺证据弃权不虚构；④后验样本 <30 走中性门（绩效因子恒 1.0），不提前升降档；⑤效应量引用须注明市场/样本期/口径，并预设 3–5 折衰减。已知缺憾：多重检验校正正典 Harvey-Liu-Zhu（t>3.0 门槛）本轮未及收录，单因子 t 值的地位应放在该框架下评估。

## 第 14 章 反证与失败模式清单

本章收录不支援主线结论的反证与失败模式，防止任何一条规则被绝对化。

①「动量缺失」是状态变量非永恒规律：6-6 动量 1998–2005 年化 11.5%、2005Q4 股改后崩溃，剔除高噪声交易股后可恢复 8.2%/年——机构化加深后 A 股动量可能回归，是 2026 之后的真实开放问题。②「暴涨后必崩」不成立：42 个市场 1900–2014，单年翻倍后次年内腰斩概率仅约 6.9%，再翻倍概率（约 26%）高于腰斩（约 15%）——GSY 的 53% 是「行业组合 + 净超额 100% + 两年窗口」的条件口径，两者必须并读（W. N. Goetzmann, "Bubble Investing: Learning from History," NBER WP 21693, 2015）。③顶部识别天然有事后性：技术革命期的「泡沫」形态可由理性学习模型产生，事前不可预测——任何确定性判别规则只应降置信、绝不反手做空（L. Pástor and P. Veronesi, "Technological Revolutions and Stock Prices," *American Economic Review*, vol. 99, no. 4, pp. 1451-1483, 2009）。④A/HK 无公告日历溢价（t≈1），event 类策略必须依赖条件筛选而非无条件事件暴露。⑤CGO 在中国的定价符号存疑，盲目移植美股方向会做反。⑥南向流量周频/日频口径冲突未决。⑦反转与换手互相解释（PMO 使反转 alpha 减半），两者同时入判据须防双计。⑧美国 PEAD 大市值段 2006 年起已消失——经典效应量不可外推到当代大票。⑨长期反转 2000 年后美股复制大幅减弱，A 股证据层级低。⑩「国家队=稳定器」有反证：2015 后国家队持股个股波动率反而上升（H. Li and K. Liu, "China's National Team: A Game Changer in Stock Market Stabilization?," *Finance Research Letters*, vol. 61, 104984, 2024）。⑪社融/信贷脉冲领先 A 股的证据唯一来源是无方法披露的博客，宏观流动性数据不作可操作择时信号。

## 第 15 章 与 vibe-stock 证据块映射表与数据缺口

结论：六个用户关切全部可映射到现有或近似数据——正向四项走 position 轨策略（direction_vote），风险三项走既有 risk.json 通道（risk_downgrade），波段走 swing_band，市场级情绪与指数基准列 Phase 5。映射以 124 条 findings 的 data_in_vibe_stock 与 operational_signal 字段归纳。

| 因子/判据 | 所需数据 | 现有证据块 | 落地通道 |
| :--- | :--- | :--- | :--- |
| EP 分位估值锚 | PE/PB 现值 + 5 年分位表 | yes（valuation，分位表插值） | direction_vote（quality_value） |
| 盈利能力稳定性 | ROE/ROIC/毛利率近 4 期 | yes（fundamentals，em 主链） | direction_vote（quality_value） |
| EPS 修正 / 预期差 | EPS 修正序列、预告 vs 一致预期 | partial（A 股无修正历史，用预告预期差代理；HK 仅 yf 源） | direction_vote（revision_momentum） |
| 异常换手 / 换手分位 | 近 20/250 日换手序列 | partial（ak-em 链首 + moneyflow/chip 回溯，标 estimated；HK not_supported） | risk_downgrade |
| 涨停计数 / MAX | 日 K 涨跌幅（代码段阈值） | yes（daily_bars，A 股标涨停饱和；HK 不标） | risk_downgrade |
| 52 周高点锚 | 现价/52 周最高 | yes（technical.pct_from_52w_high，口径略偏） | direction_vote 组合条件（weakened 降档） |
| 政策四级分层 | 规划清单、部委文件、中标/补贴公告、预告 | partial（industry/notices/forecast/news 拼合，L1 清单静态维护） | direction_vote（policy_staged）+ risk_downgrade |
| 监管敏感行业 | 行业清单 + 官媒点名/征求意见稿 | no（静态策规维护） | risk_downgrade（触发即 veto/downgrade） |
| 解禁日历 | 解禁日期/比例/类型 | yes（unlock，A 股；HK not_supported） | risk_downgrade |
| 抢跑透支 / 隔夜-日内拆分 | 披露日历、20 日涨幅、open/close | yes（forecast.next_disclosure + daily_bars） | risk_downgrade |
| 高送转 × 减持并发 | 公告分型 | partial（notices 标题匹配） | risk_downgrade（severity=high 候选） |
| 壳 / 退市闸 | ST 标识、总市值 | yes（quote.name / total_mv_yi） | risk_downgrade（强制降级/veto） |
| 困境度 + 催化 | 负债率分位、连续亏损、预告/盈喜 | partial（负债率/净利近 4 期可得；现金流表缺） | direction_vote（turnaround_catalyst） |
| 波段 regime 与带宽 | VR、箱体、MA150/200、σ_d、成本表 | partial（daily_bars 可推导；成本常量表需新增并官方重验） | swing_band（band_lo/band_hi/trail_ref） |
| 低波动分位 | 250 日已实现波动（文献口径 36 个月） | partial（口径差异注记） | direction_vote 组合条件 |
| 季节性（同月收益） | ≥3 年月度收盘 | no（BARS_WINDOW=250 不足） | info_only（Phase 5） |
| 市场级情绪（两融/新开户/ERP） | 两融余额、开户数、指数 PE/国债序列 | no（个股级换手/涨停/估值分位代理） | info_only（Phase 5） |
| 指数日 K（超额判定/指数 regime） | HS300/HSI 日线 | no（σ√h 缩放带先行替代） | info_only（Phase 5，与 07-monitor P3 共用接入） |
| 南向持股变化 | 南向持股比环比 | partial（moneyflow.hk，T-1；口径敏感） | info_only（佐证） |
| AI 主题热度 / 题材真伪 | 新闻词频、板块排名、订单/收入对照 | partial（news 10 条 + industry 当日排名） | risk_downgrade + info_only |

数据缺口清单（均列 Phase 5 另行评审）：指数日 K 取数链（超额判定带）、A 股 EPS 修正历史（Phase 4 逐篇回收后仍仅 ak-em 链首可得）、市场级情绪块（两融/新开户/ERP）、BARS_WINDOW 扩至 500 根（12-1 精确动量、GSY 两年窗、季节性——会改变 pct_from_52w 与 CYQ 筹码语义，属规约级冲突须人工评审）。

## 附：拒绝引入清单

以下候选在方案比选中被显式拒绝（拒绝理由的证据锚见括号内 finding 编号）：

| 候选 | 拒绝理由（要点） |
| :--- | :--- |
| 美股式 12-1 动量追高策略（momentum YAML） | A 股全样本动量 0.198%/月 t=0.71 不显著（anomalies-03/04、behavioral-22），仅高价低散户子集成立且需全市场分位；反转与换手互相解释。只保留「强势股不追高」反转警戒并入既有策略 |
| 52 周高点锚定作独立方向票 | CH-4 调整后不显著（0.78/t=1.64），计成本后多数市场无利润（anomalies-06 weakened）。只作 quality_value 组合条件 |
| 无条件网格 / 自动高抛低吸 | 随机游走下网格期望净负、趋势段等价做空跨式且尾部无界；再平衡溢价仅约 1-3pct/年且 regime 条件（math-position-07/03）。只保留 regime 门控带宽纪律版 |
| 公告日历溢价（持券等公告） | 46 国样本中国/香港点估计不显著 t≈1（events-05）。披露日临近只触发利好出尽风险检查 |
| 指数日 K 取数链 + 超额判定带（v1 即做） | 需新增 fetch 簇且指数接口未实测（探针缺失）；σ√h 带已消除 ±2% 长期限退化。列 Phase 5 |
| BARS_WINDOW 全局扩至 500 根 | 改变 pct_from_52w 与 CYQ 筹码语义、波及 golden 与大量 selftest，规约级冲突待人工评审。v1 用近似 + 降置信注记 |
| 中线引入 add/trim 新动作词 | ACTION_OF / families / postmortem.SCORABLE 三处连锁扩表；现有信号 + 分批节奏语义已可表达 |
| 台账键前缀 position\|<source>（单一 ledger） | postmortem 断言会红、performance_factor 需改签名；分文件方案裁决器零改动、存量逐字节兼容——技术优劣一边倒 |
| 中线信号恒登记 | 打破「一次 report 一条信号」的 selftest 假设；按文件存在可选开启使行为与现状等价 |
| 市场级情绪/钟摆扩展块（两融、新开户、ERP） | 方向正确（behavioral-17/19/20）但需 2-4 个新零权重块与取数簇；v1 以个股级换手/涨停/估值分位代理，跑顺后按 backlog 评审 |
| TMT 成交占比 40% 硬阈值 | unverifiable（MSCI 指标未获一手确认、广发口径无公开渠道且 2025 自认失效）。只作 news 注记并注明「非结构常数」 |
| 美林时钟 / 货币-信用四象限 / M1-社融 / EPU 择时 | 均 unverifiable（无可核回测、2008 后判别力弱化、社融领先证据唯一来源为无方法披露博客）；M2 公告前无显著漂移。拒绝作 regime 信号 |
| 高增长线性外推 / 美式 F-score 高 BM 用法 / AH 收敛套利 / CGO 方向因子 / 南向方向票 | 盈利年约 38% 均值回复与成长 ≈ 随机（tq-01/02）；A 股 F-score 溢价在低 BM 侧（tq-06）；押 AH 收敛长期大亏（policy-13）；CGO 符号未证实、南向口径敏感（均 weakened）。一律以降级形态保留价值 |

## 数据与核验状态

本报告为结论层产物：完整 findings 数据（含每条的 URL、source_tier、verify.verdict 与 correction 全文）存于 `.temp/wf1_result.json`（本仓不入库的临时产物），报告只承载结论、引文与降权标记。核验统计须区分两套口径：124 条为调研 findings 总数（confirmed 100 / weakened 20 / unverifiable 4，refuted 0）；正文以 IEEE 引文形式显式引用约 68 条（按期刊卷期、SSRN、Working Paper 三类条目模式计数），其中显式标注「核验：weakened」16 处、「核验：unverifiable」2 处。weakened 的主要形态是引文卷期页错误与效应量转述失真（本报告已按 verify.correction 修正后引用并显式标注），unverifiable 均为 practitioner 档且只作注记。本报告不构成投资建议。
