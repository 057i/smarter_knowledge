import asyncio
import json

from langchain.agents import create_agent
from langchain_mcp_adapters.client import MultiServerMCPClient

from conf.mcp_config import mcp_config
from core.load_prompt import load_prompt
from core.logger import logger
from utils.llm_util import get_llm_client


async def query_by_mcp_agent(query: str):
    """

    """
    try:
        client = MultiServerMCPClient(
            {
                "bailian_search": {  #
                    "transport": "streamable_http",
                    "url": mcp_config.mcp_base_url,
                    "headers": {"Authorization": mcp_config.api_key},
                    "timeout": 300,
                    "sse_read_timeout": 300,

                }
            }
        )
        tools = await client.get_tools()

        llm = get_llm_client()
        agent = create_agent(model=llm, tools=tools)

        # prompt = load_prompt("mcp_prompt", query=query)
        result = await agent.ainvoke({
            "messages": [("user", query)]
        })

        # 提取tool_message就是调用工具
        docs = []

        if result:
            for message in result["messages"]:
                if message.type == "tool" and isinstance(message.content, list):
                    target_content = message.content[0]
                    text = target_content.get("text")
                    text_dict = json.loads(text)

                    logger.info(f"pages：{type(text_dict)}{text_dict}")

                    pages = text_dict.get("pages", [])

                    for page in pages:
                        docs.append({
                            "snippet": page.get("snippet", ""),
                            "title": page.get("title", ""),
                            "url": page.get("url", ""),
                        })

        logger.info(f"结果：{docs}")
        return docs
    except Exception as e:
        logger.error(f"获取工具列表失败: {e}", exc_info=True)
        raise RuntimeError(f"获取mcp工具列表失败{e}")


if __name__ == "__main__":
    asyncio.run(query_by_mcp_agent(
        "RS PRO RS-12数字万用表的规格什么样?"))

content = {"pages": [{
    "snippet": "RS PRO RS12, 数字显示器 手持式 万用表, 最大600 V 交流, 最大600 V 直流 10 A 直流, 最大2 mΩ 客户支持行业资源超值优惠 包裹跟踪 登录/注册 0 菜单 制造商编号 / 测试与测量 / 万用表和附件 / 万用表 RS 库存编号: 123-1939 制造商: RS PRO 查看所有万用表 可享批量折扣 查看批量定价选项 小计(1 件)* RMB118.18 (不含税) RMB133.54 (含税) 单位 选择或输入数量 有库存 209件可立即发货 另外654件将从其他地点发货 另外250件在2026年10月14日发货 **需要更多产品?**输入您需要的数量,点击“查看送货日期”,查看库存和送货信息。 批量定价选项 单位 每单位 1 - 4RMB118.18 5 +RMB95.37 * 参考价格 比较 添加到收藏夹 产品技术参数 产品技术参数资料 法例与合规 产品详细信息 通过选择一个或多个属性来查找类似产品。 选择全部 属性值 品牌RS PRO 产品类型万用表 万用表类型手持式 型号RS12 电阻值分辨率100mΩ 显示器类型数字 功能测量交流电压, 直流电流, 直流电压, 电阻值 最大交流电压测量600V 交流 最大直流电压测量600V 直流 最大电阻测量2mΩ 最大直流电流测量10A 直流 真有效值否 直流电压精度±0.5 % rdg + 2 Digits 直流电流精度±1 % rdg + 2 Digits 交流电压精度±1.2 % rdg + 10 Digits",
    "hostname": "无", "hostlogo": "",
    "title": "RS PRO RS12, 数字显示器 手持式 万用表, 最大600 V 交流, 最大600 V 直流 10 A 直流, 最大2 mΩ",
    "url": "http://rsonline.cn/mobile/p/digital-multimeters/1231939/"}, {
    "snippet": "商品RS Pro欧时 , RS12, 手持式 数字万用表 2MΩ 70 x 48 x 150mm 交流电压、直流电流、直流电压、电阻 关注 暂无报价降价提醒 商品介绍完善信息 待完善 好价爆料全网内容 (5)商品口碑 全网内容(5) 0 完善信息 商品报错",
    "hostname": "什么值得买",
    "hostlogo": "https://img.alicdn.com/imgextra/i4/O1CN01ZlIGDT1md3nZaVmXr_!!6000000004976-55-tps-32-32.svg",
    "title": "RS Pro欧时 , RS12, 手持式 数字万用表 2MΩ 70 x 48 x 150mm 交流电压、直流电流、直流电压、电阻 ",
    "url": "https://wiki.smzdm.com/p/8wxe3vq/"}, {
    "snippet": "RS PRO S1 真有效值, 数字显示器 手持式 万用表, 最大1 kV ac, 最大交流电流测量10 A 交流, 最大1 kV dc 10 A 直流, 最大40 mΩ 客户支持行业资源超值优惠 包裹跟踪 登录/注册 0 菜单 制造商编号 / 测试与测量 / 万用表和附件 / 万用表 RS 库存编号: 199-3846 制造商: RS PRO 查看所有万用表 可享批量折扣 小计(1 件)* ¥1,681.50 (不含税) ¥1,900.10 (含税) 单位 选择或输入数量 查看送货日期 有库存 42件将从其他地点发货 另外100件在2026年11月03日发货 **需要更多产品?**输入您需要的数量,点击“查看送货日期”,查看库存和送货信息。 单位 每单位 1 - 4RMB1,681.50 5 +RMB1,383.88 * 参考价格 比较 产品技术参数 产品技术参数资料 法例与合规 产品详细信息 通过选择一个或多个属性来查找类似产品。 选择全部 属性值 品牌RS PRO 万用表类型手持式 产品类型万用表 型号S1 显示器类型数字 电阻值分辨率0.01mΩ 功能测量交流电流, 交流电压, 电容值, 断通, 直流电流, 直流电压, 二极管测试, 频率, 电阻值 最大交流电流测量10A 交流 最大直流电流测量10A 直流 最大交流电压测量1kV ac 最大直流电压测量1kV dc 最大电阻测量40mΩ 真有效值是 交流电压精度±1.0 % rdg + 3 Digits 直流电压精度±0.5 % rdg + 2 Digits 交流电流精度±1.5 % rdg + 3 Digits 直流电流精度±1 % rdg + 3 Digits 交流电流分辨率0.01A 交流",
    "hostname": "无", "hostlogo": "",
    "title": "RS PRO S1 真有效值, 数字显示器 手持式 万用表, 最大1 kV ac, 最大交流电流测量10 A 交流, 最大1 kV dc 10 A 直流, 最大40 mΩ",
    "url": "https://rsonline.cn/web/p/multimeters/1993846/"}, {
    "snippet": "RS PRO RS14, 数字显示器 手持式 万用表, 最大600 V 交流, 最大交流电流测量10 A 交流, 最大600 V 直流 10 A 直流, 最大20 mΩ 客户支持行业资源超值优惠 包裹跟踪 登录/注册 0 菜单 制造商编号 / 测试与测量 / 万用表和附件 / 万用表 RS 库存编号: 123-1938 Distrelec 货号: 304-02-616 制造商: RS PRO 查看所有万用表 小计(1 件)* ¥317.56 (不含税) ¥358.84 (含税) 单位 选择或输入数量 有库存 另外197件在2026年4月06日发货 另外1,825件在2026年4月06日发货 另外1,170件在2026年6月12日发货 **需要更多产品?**输入您需要的数量,点击“查看送货日期”,查看库存和送货信息。 单位 每单位 1 +RMB317.56 * 参考价格 产品技术参数 产品技术参数资料 法例与合规 通过选择一个或多个属性来查找类似产品。 选择全部 属性值 品牌RS PRO 产品类型万用表 万用表类型手持式 型号RS14 显示器类型数字 电阻值分辨率100mΩ 功能测量交流电流, 交流电压, 直流电流, 直流电压, 电阻值, 温度 最大直流电压测量600V 直流 最大直流电流测量10A 直流 最大交流电压测量600V 交流 最大交流电流测量10A 交流 最大电阻测量20mΩ 真有效值否 交流电流精度±1.5 % rdg ± 5 Digits 直流电压精度±0.5 % rdg ± 2 Digits 交流电压精度±1.2 % rdg ± 3 Digits 直流电流精度±1 % rdg ± 3 Digits 直流电流分辨率0.1μA 直流 交流电压分辨率0.1mV 交流 直流电压分辨率0.1 mV dc",
    "hostname": "无", "hostlogo": "",
    "title": "RS PRO RS14, 数字显示器 手持式 万用表, 最大600 V 交流, 最大交流电流测量10 A 交流, 最大600 V 直流 10 A 直流, 最大20 mΩ",
    "url": "https://rsonline.cn/web/p/digital-multimeters/1231938/"}, {
    "snippet": "直插头 装有熔断器 装有保险丝的探头套件, 1.2 m线长, cat iii rs 库存编号 : 204-599制造商 : rs pro点击缩放查看所有万用表表笔 小计(1 件)* ¥402.62 (不含税) ¥454.96 (含税) add to basket单位选择或输入数量查看送货日期添加到购物车有库存另外 25 件在 2026年4月27日 发货另外 45 件在 2026年4月30日 发货 **需要更多产品?**输入您需要的数量,点击“查看送货日期”,查看库存和送货信息。单位每单位 1 + rmb402.62 * 参考价格比较添加到收藏夹 rs 库存编号 : 204-599制造商 : rs pro产品技术参数产品技术参数资料法例与合规产品详细信息通过选择一个或多个属性来查找类似产品。品牌 rs pro 引线型 装有保险丝的探头套件 产品类型 万用表线 连接器类型 直插头 装有熔断器 是 引线长度 1.2m 安全类别电压 1000v 最低工作温度 -10°c 最高工作温度 150°c 安全类别等级 cat iii 标准/认证 gs 38, and 2015/863 查找类似产品选择全部 品牌 rs pro 引线型 装有保险丝的探头套件",
    "hostname": "无", "hostlogo": "",
    "title": "RS PRO 万用表线 直插头 装有熔断器 装有保险丝的探头套件, 1.2 m线长, CAT III",
    "url": "https://rsonline.cn/mobile/p/products/204599/"}],
    "request_id": "25c8ac21-d595-9a4a-81a6-b19871ae8257", "tools": [], "status": 0}
content = [{'type': 'text',
            'text': '{"pages":[{"snippet":"RS PRO RS12, 数字显示器 手持式 万用表, 最大600 V 交流, 最大600 V 直流 10 A 直流, 最大2 mΩ 客户支持行业资源超值优惠 包裹跟踪 登录/注册 0 菜单 制造商编号 / 测试与测量 / 万用表和附件 / 万用表 RS 库存编号: 123-1939 制造商: RS PRO 查看所有万用表 可享批量折扣 查看批量定价选项 小计(1 件)* RMB118.18 (不含税) RMB133.54 (含税) 单位 选择或输入数量 有库存 209件可立即发货 另外654件将从其他地点发货 另外250件在2026年10月14日发货 **需要更多产品?**输入您需要的数量,点击“查看送货日期”,查看库存和送货信息。 批量定价选项 单位 每单位 1 - 4RMB118.18 5 +RMB95.37 * 参考价格 比较 添加到收藏夹 产品技术参数 产品技术参数资料 法例与合规 产品详细信息 通过选择一个或多个属性来查找类似产品。 选择全部 属性值 品牌RS PRO 产品类型万用表 万用表类型手持式 型号RS12 电阻值分辨率100mΩ 显示器类型数字 功能测量交流电压, 直流电流, 直流电压, 电阻值 最大交流电压测量600V 交流 最大直流电压测量600V 直流 最大电阻测量2mΩ 最大直流电流测量10A 直流 真有效值否 直流电压精度±0.5 % rdg + 2 Digits 直流电流精度±1 % rdg + 2 Digits 交流电压精度±1.2 % rdg + 10 Digits","hostname":"无","hostlogo":"","title":"RS PRO RS12, 数字显示器 手持式 万用表, 最大600 V 交流, 最大600 V 直流 10 A 直流, 最大2 mΩ","url":"http://rsonline.cn/mobile/p/digital-multimeters/1231939/"},{"snippet":"商品RS Pro欧时 , RS12, 手持式 数字万用表 2MΩ 70 x 48 x 150mm 交流电压、直流电流、直流电压、电阻 关注 暂无报价降价提醒 商品介绍完善信息 待完善 好价爆料全网内容 (5)商品口碑 全网内容(5) 0 完善信息 商品报错","hostname":"什么值得买","hostlogo":"https://img.alicdn.com/imgextra/i4/O1CN01ZlIGDT1md3nZaVmXr_!!6000000004976-55-tps-32-32.svg","title":"RS Pro欧时 , RS12, 手持式 数字万用表 2MΩ 70 x 48 x 150mm 交流电压、直流电流、直流电压、电阻 ","url":"https://wiki.smzdm.com/p/8wxe3vq/"},{"snippet":"RS PRO S1 真有效值, 数字显示器 手持式 万用表, 最大1 kV ac, 最大交流电流测量10 A 交流, 最大1 kV dc 10 A 直流, 最大40 mΩ 客户支持行业资源超值优惠 包裹跟踪 登录/注册 0 菜单 制造商编号 / 测试与测量 / 万用表和附件 / 万用表 RS 库存编号: 199-3846 制造商: RS PRO 查看所有万用表 可享批量折扣 小计(1 件)* ¥1,681.50 (不含税) ¥1,900.10 (含税) 单位 选择或输入数量 查看送货日期 有库存 42件将从其他地点发货 另外100件在2026年11月03日发货 **需要更多产品?**输入您需要的数量,点击“查看送货日期”,查看库存和送货信息。 单位 每单位 1 - 4RMB1,681.50 5 +RMB1,383.88 * 参考价格 比较 产品技术参数 产品技术参数资料 法例与合规 产品详细信息 通过选择一个或多个属性来查找类似产品。 选择全部 属性值 品牌RS PRO 万用表类型手持式 产品类型万用表 型号S1 显示器类型数字 电阻值分辨率0.01mΩ 功能测量交流电流, 交流电压, 电容值, 断通, 直流电流, 直流电压, 二极管测试, 频率, 电阻值 最大交流电流测量10A 交流 最大直流电流测量10A 直流 最大交流电压测量1kV ac 最大直流电压测量1kV dc 最大电阻测量40mΩ 真有效值是 交流电压精度±1.0 % rdg + 3 Digits 直流电压精度±0.5 % rdg + 2 Digits 交流电流精度±1.5 % rdg + 3 Digits 直流电流精度±1 % rdg + 3 Digits 交流电流分辨率0.01A 交流","hostname":"无","hostlogo":"","title":"RS PRO S1 真有效值, 数字显示器 手持式 万用表, 最大1 kV ac, 最大交流电流测量10 A 交流, 最大1 kV dc 10 A 直流, 最大40 mΩ","url":"https://rsonline.cn/web/p/multimeters/1993846/"},{"snippet":"RS PRO RS14, 数字显示器 手持式 万用表, 最大600 V 交流, 最大交流电流测量10 A 交流, 最大600 V 直流 10 A 直流, 最大20 mΩ 客户支持行业资源超值优惠 包裹跟踪 登录/注册 0 菜单 制造商编号 / 测试与测量 / 万用表和附件 / 万用表 RS 库存编号: 123-1938 Distrelec 货号: 304-02-616 制造商: RS PRO 查看所有万用表 小计(1 件)* ¥317.56 (不含税) ¥358.84 (含税) 单位 选择或输入数量 有库存 另外197件在2026年4月06日发货 另外1,825件在2026年4月06日发货 另外1,170件在2026年6月12日发货 **需要更多产品?**输入您需要的数量,点击“查看送货日期”,查看库存和送货信息。 单位 每单位 1 +RMB317.56 * 参考价格 产品技术参数 产品技术参数资料 法例与合规 通过选择一个或多个属性来查找类似产品。 选择全部 属性值 品牌RS PRO 产品类型万用表 万用表类型手持式 型号RS14 显示器类型数字 电阻值分辨率100mΩ 功能测量交流电流, 交流电压, 直流电流, 直流电压, 电阻值, 温度 最大直流电压测量600V 直流 最大直流电流测量10A 直流 最大交流电压测量600V 交流 最大交流电流测量10A 交流 最大电阻测量20mΩ 真有效值否 交流电流精度±1.5 % rdg ± 5 Digits 直流电压精度±0.5 % rdg ± 2 Digits 交流电压精度±1.2 % rdg ± 3 Digits 直流电流精度±1 % rdg ± 3 Digits 直流电流分辨率0.1μA 直流 交流电压分辨率0.1mV 交流 直流电压分辨率0.1 mV dc","hostname":"无","hostlogo":"","title":"RS PRO RS14, 数字显示器 手持式 万用表, 最大600 V 交流, 最大交流电流测量10 A 交流, 最大600 V 直流 10 A 直流, 最大20 mΩ","url":"https://rsonline.cn/web/p/digital-multimeters/1231938/"},{"snippet":"直插头 装有熔断器 装有保险丝的探头套件, 1.2 m线长, cat iii rs 库存编号 : 204-599制造商 : rs pro点击缩放查看所有万用表表笔 小计(1 件)* ¥402.62 (不含税) ¥454.96 (含税) add to basket单位选择或输入数量查看送货日期添加到购物车有库存另外 25 件在 2026年4月27日 发货另外 45 件在 2026年4月30日 发货 **需要更多产品?**输入您需要的数量,点击“查看送货日期”,查看库存和送货信息。单位每单位 1 + rmb402.62 * 参考价格比较添加到收藏夹 rs 库存编号 : 204-599制造商 : rs pro产品技术参数产品技术参数资料法例与合规产品详细信息通过选择一个或多个属性来查找类似产品。品牌 rs pro 引线型 装有保险丝的探头套件 产品类型 万用表线 连接器类型 直插头 装有熔断器 是 引线长度 1.2m 安全类别电压 1000v 最低工作温度 -10°c 最高工作温度 150°c 安全类别等级 cat iii 标准/认证 gs 38, and 2015/863 查找类似产品选择全部 品牌 rs pro 引线型 装有保险丝的探头套件","hostname":"无","hostlogo":"","title":"RS PRO 万用表线 直插头 装有熔断器 装有保险丝的探头套件, 1.2 m线长, CAT III","url":"https://rsonline.cn/mobile/p/products/204599/"}],"request_id":"d1a6c501-ae38-9149-bc7d-e9ba0f9ac8ef","tools":[],"status":0}',
            'id': 'lc_440c01f2-d479-455b-9445-696fc23f7e7c'}]
name = 'bailian_web_search'
id = '060407f6-3d51-4ca3-b207-e4698cb02a9f'
tool_call_id = 'call_cfa423fd929840b4a3546541'
