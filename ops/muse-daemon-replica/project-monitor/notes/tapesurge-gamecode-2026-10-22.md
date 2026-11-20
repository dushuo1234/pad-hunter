# TapeSurge 游戏代码调查 — 2026-10-22 22:20 (UTC+8)

## 拉取的东西
- https://tapesurge.com/ → 和 /tmp/tapesurge.html 一样（SPA 壳），只引用了 ./assets/index-DcP5DhCd.js（约 293 KB）和 style-CD0ILa9L.css
- 没有懒加载 chunk，没有动态 import()。index-DcP5DhCd.js.map 返回 404。sitemap.xml 和 manifest.json 也是 404
- 白皮书 HTML 在 /whitepaper（./whitepaper.html 是空的）。白皮书 Markdown 原文：https://tapesurge.com/TapeSurge-whitepaper-V4.1.md（44 KB），已复制到 notes/tapesurge-whitepaper-V4.1.md

## 前端（index-DcP5DhCd.js）
- 技术栈：React 19 加 lucide 图标。代码里没有 ethers、viem、wagmi、web3、window.ethereum、eth_requestAccounts、walletconnect、RPC、chainId，也没有 ABI 或 stateMutability
- 唯一的 fetch() 是 Vite 的 modulepreload 辅助函数，没有任何 API 调用
- 只出现了这几个地址：
  - it = 0x04B649076a11819EF7AdA36e02DD55e0923550Ee（基金会 Safe，只用于 bscscan 链接）
  - at = 0x…dEaD
  - BEM 0x5ce0…695a（指向 bscscan token 页的链接）
- 所谓「游戏」部分全是展示组件：
  - 主板动画演示，配文「交互演示 · 不连接钱包」「Interactive illustration. No onchain transactions.」，按钮有 Play demo / Pause / Replay，步骤 BEM→PoD→Pulse
  - 收益测算器（组件 gt），APR 下拉只有 70 / 100 / 129 三个选项，写死成「投入 1 BEM + 0.01 BEM 入场费」，按示例情景计算（标准局假设 500 人，月局假设 100 BEM 池子）
  - 分账饼图：回购 40%，主板全部结束后变成 70%；基金会 20%；其余比例
- 代码里唯一的 Math.random 是 React 内部生成 key 用的，和抽奖无关。没有倒计时，也没有 setInterval 轮次计时
- 前端讲的随机数方案：「运营地址发起开奖，Chainlink VRF 提供可验证随机数」
- 结论：前端没有任何游戏逻辑，也没有合约接线，全部是 mock 和文案

## 白皮书里的合约规格（只是设计，未部署）
- GenesisSplitter：
  - 构造函数调用 TapeOut 工厂 createCPU("TapeSurge Genesis", …, 66666, 0.001 BNB)
  - distribute()：铸造收入按 40 / 10 / 20 / 30 分配
  - buyback()：分批买 BEM 后打进 0x…dEaD，每次最多 0.5 BNB，间隔至少 1 小时，按 TWAP 设 98% 最低成交量
  - claimReward(i)：i 为 1 到 5
- BoardFactory：
  - startGenesis()：铸满 10,000 颗或开铸满 7 天后，任何人都能调用
  - 下一块主板的规模自动乘以 1.25 / 1 / 0.75 / 0.5，范围 100–1,000 BEM
- TapeBoard（标准局）：
  - join(passId, amount)
  - 荷兰式拍卖收购矿机
  - harvest()
  - 运营地址开奖，经 VRF 回调；淘汰权重为「其余所有人的投入之和」，实现上用树状数组加二分查找
  - finalize() 按 65 / 30 / 3 / 2 分配
- MonthBoard（月局）：
  - join(passId, amount)
  - 准备期 3 天，挖矿期 30 天
  - drawPrizes() 和 finalizePrizes() 开 5 个奖，比例 60 / 15 / 15 / 5 / 5，各奖独立抽取
  - 本金按成本价交接或挂单
- 随机数：Chainlink VRF v2.5 订阅模式，callbackGasLimit 750,000；24 小时没回调可以重新请求，只认最新一次请求；备选方案是 drand evmnet。白皮书明确说不用 blockhash
- 附录 C 写着「TapeSurge 合约：待部署」。附录 D 的测试网参数里写「运营地址测试网先用部署者地址」
- 白皮书只写了 BSC，没有提 X Layer

## 链上核查
- BSC 测试网（chainId 97）：Foundation Safe、Fee Safe、BEM、PoD、工厂地址上都没有代码
- X Layer（chainId 196）：Foundation Safe 0x04B6…50Ee 已部署，nonce 为 1，3/5 多签
  - 签名人和 BSC 上基本一致，只把 0x02e5… 换成了 0xd2ff90b88e6b3703913f60446339bde848fa8768
  - 这说明他们真的在为 X Layer 做准备
- X Layer 测试网（chainId 1952）：这些地址上都没有代码
- BSC 上 Foundation Safe 签名人（3/5）：0x02e5…f65d、0x9faa…cfef、0x36c5…eb78、0xf2d7…7a7e、0x0743…89c6
- BSC 上 Fee Safe 签名人（2/3）：0x9304…d965、0x4c0a…9229、0x7b88…8918
- 签名人在 BSC 测试网上的活动：0xf2d7 nonce 11，0x9304 nonce 1。按 CREATE 推导 0xf2d7 的部署地址，有两个合约：
  - 0x99fa366789e98a784f3ed4d61e1e595a7bb12ea9（nonce 0）
  - 0xff581973400b6037977a770c7987cedd56ae6af5（nonce 9）
  - 两个合约的函数选择器都是 bem()、treasury()=0xf2d7、referee()=0x8a5b…6b47、reviewer()=0x9e1d…4856、feeBps()=1000、faucetReserve、getMatch(bytes32)、report(bytes32,bytes32)、appeal(bytes32)、finalize(bytes32)、cancel(bytes32,bytes)、refundExpired(bytes32)、claimable(uint8,address)、claimNative()，以及 EIP712 和 ECDSA 相关函数
  - bem() 指向 0x9765c510b2899b5d75f59f82bbe73a1de44e634b，代币名「Arena Test BEM (no value)」，符号 tBEM
  - 这是一个 BEM 对战 / 竞技场托管合约（带裁判、申诉、过期退款），不是 TapeSurge 的抽签主板：没有 VRF 回调 rawFulfillRandomWords，也没有 join、drawPrizes、startGenesis
  - 它是 Safe 签名人旗下的另一个产品，只能算旁证
- GitHub：
  - 搜 repo 或代码里的 TapeSurge、TapeBoard、MonthBoard、"finalizePrizes drawPrizes startGenesis"，都没有找到 TapeSurge 源码
  - 搜网表 hash 0xfffa29f1…，只命中 ddgsdde/tap 的 TapeOut 网表快照（task-017 半加器电路），这是第三方的 TapeOut 数据仓库
- BscScan 页面被 Cloudflare 挡住；Sourcify 在 56 和 97 上查 BEM、PoD 和两个测试网合约，结果都是 match:null，没有验证源码

## ⚠️ 主网上已有两个同名 TapeOut processor（据 ddgsdde/tap 的 processors-registered.json，快照区块 129111338，2026-10-22 18:09 UTC+8）
1. processor 0x051514211ecC44AC3681FccADfe09063b5BC6fdF，name「TapeSurge」
   - transistors 0xb67603d2914b5E301b63235972dBCa89634fCc5f：supplyCap=66,666，mintPrice=0.001 BNB，minted=0
   - 参数和白皮书完全一致
   - creator()=0x58d4a4aeae698962e65c6a59606b194fa8ef9221，是个 EOA，nonce 1，余额约 0.009 BNB
   - 白皮书说创建者应该是 GenesisSplitter 合约，名称应该是「TapeSurge Genesis」。这个 EOA 不是任何一个 Safe 的签名人
   - 判断：高概率是照抄白皮书参数的仿盘，或者有人抢注。**不是 CA，不要推送**
2. processor 0xA8b39718068551BCbC219EB022C9F42e3D4b23B3，name「TapeSurge」
   - transistors 0x854cBE1ED9476E0734E39c9aB92C8362E018c37A：cap=1,000,000，mintPrice=0.0001 BNB，minted=0
   - creator 0x3b57d84f…4444，EIP-7702 委托 EOA，nonce 552
   - 判断：仿盘
- 两个都还没人铸造。这和 @TapeSurge 和 @superwang 发的「已经有假的了」的警告一致

## 风险点（按白皮书设计）
- 运营地址（由手续费 Safe 任命）掌握：开奖时机（只能在到期后）、VRF 重新请求、分批发放、月局矿机交接和**挂单定价**
  - 合约读不到二级市场价格，挂单价由项目方填，溢价部分要信任项目方
  - 私钥泄露的话，攻击者可以按成本价把矿机挂出去
- 「只认最新请求」加上 24 小时可以重新请求：如果实现有问题，运营方可能借重新请求影响结果，需要审计确认旧回调确实作废
- 设计上没有 owner 提款，也不可升级；过期 365 天未领的资金转给基金会
- 依赖外部 TapeOut Beacon 代理，升级由工厂 3/5 多签控制，有「升级哨兵」机制
- 以上全部无法核实，因为合约源码没公开，测试网合约也找不到

## 完成度（已写入 watchlist.json 和 candidates.json，含镜像）
- js_completion=0.15 (low)，contract_code_completion=0.25 (low)，game_code_completion=0.05 (low)，high_completion=false
- completion_source=manual_review:tapesurge-gamecode-2026-10-22
- 没有改 listing_at，没有改 CA 门禁；测试网地址和仿 processor 都不是 CA
