import datetime
import os
import pandas as pd
import akshare as ak
import traceback

from src.data.cache import get_cache
from src.data.models import (
    CompanyNews,
    CompanyNewsResponse,
    FinancialMetrics,
    FinancialMetricsResponse,
    Price,
    PriceResponse,
    LineItem,
    LineItemResponse,
    InsiderTrade,
    InsiderTradeResponse,
    CompanyFactsResponse,
)

# Global cache instance
_cache = get_cache()

# 中文到英文的财务术语映射字典
finance_terms_mapping = {
    # 特别关注的关键财务术语映射（优先级高）
    # "经营活动产生的现金流量净额": "free_cash_flow",
    # "利润总额": "ebit",
    # "支付利息、手续费及佣金的现金": "interest_expense",
    # "购建固定资产、无形资产和其他长期资产所支付的现金": "capital_expenditure",
    # "净利润": "net_income",
    # "负债合计": "total_liabilities",
    # "资产总计": "total_assets",
    # "流动资产合计": "current_assets",
    # "流动负债合计": "current_liabilities",
    # "分配股利、利润或偿付利息所支付的现金": "dividends_and_other_cash_distributions",
    # "研发费用": "research_and_development",
    # "营业费用": "operating_expense",
    # "营业利润": "operating_income",
    # "货币资金": "cash_and_equivalents",
    # "所有者权益(或股东权益)合计": "shareholders_equity",
    # "商誉": "goodwill",
    # "无形资产": "intangible_assets",
    # "基本每股收益": "earnings_per_share",
    # "营业收入": "revenue",
    
    # # 组合映射
    # "商誉和无形资产": "goodwill_and_intangible_assets",
    
    # # 通用术语
    # "报告日": "report_date",
    # "数据源": "data_source",
    # "是否审计": "is_audited",
    # "公告日期": "announcement_date",
    # "币种": "currency",
    # "类型": "type",
    # "更新日期": "update_date",
    "TOTAL_CURRENT_ASSETS":"current_assets",
    "TOTAL_CURRENT_LIAB":"current_liabilities",
    "GOODWILL":"goodwill",
    "NETPROFIT":"net_income",
    "TOTAL_OPERATE_INCOME":"revenue",
    "TOTAL_ASSETS":"total_assets",
    "TOTAL_LIABILITIES":"total_liabilities",
    "MONETARYFUNDS":"cash_and_equivalents",
    "CONSTRUCT_LONG_ASSET":"capital_expenditure",
    "ASSIGN_DIVIDEND_PORFIT":"dividends_and_other_cash_distributions",
    "BASIC_EPS":"earnings_per_share",
    "OPERATE_PROFIT":"ebit",
    "FE_INTEREST_EXPENSE":"interest_expense",
    "ACCEPT_INVEST_CASH":"issuance_or_purchase_of_equity_shares",
    "TOTAL_OPERATE_COST":"operating_expense",
    "OPERATE_PROFIT":"operating_income",
    "RESEARCH_EXPENSE":"research_and_development",
    "TOTAL_PARENT_EQUITY":"shareholders_equity"
}


def get_prices(ticker: str, start_date: str, end_date: str) -> list[Price]:
    """Fetch price data from cache or API using AKShare."""
    # Check cache first
    if cached_data := _cache.get_prices(ticker):
        # Filter cached data by date range and convert to Price objects
        filtered_data = [Price(**price) for price in cached_data if start_date <= price["time"] <= end_date]
        if filtered_data:
            return filtered_data

    # If not in cache or no data in range, fetch from AKShare API
    try:
        # 确保日期格式是字符串
        if isinstance(start_date, datetime.date):
            start_date = start_date.strftime('%Y-%m-%d')
        if isinstance(end_date, datetime.date):
            end_date = end_date.strftime('%Y-%m-%d')
            
        # 获取股票历史数据，适配不同市场
        if ticker.startswith(('6', '5', '9', '7')):  # 上海股票
            symbol = f"sh{ticker}"
        else:  # 深圳股票
            symbol = f"sz{ticker}"
        
        # 尝试获取A股历史数据
        stock_df = ak.stock_zh_a_hist(symbol=ticker, period="daily", 
                                    start_date=start_date.replace("-", ""), 
                                    end_date=end_date.replace("-", ""), 
                                    adjust="hfq")
        
        # 如果A股获取失败，尝试获取指数数据
        if stock_df.empty:
            stock_df = ak.stock_zh_index_daily_em(symbol=symbol)
        
        # 将数据转换为Price对象列表
        prices = []
        for _, row in stock_df.iterrows():
            date_str = row['日期'] if '日期' in stock_df.columns else row['date']
            if isinstance(date_str, pd.Timestamp) or isinstance(date_str, datetime.date):
                date_str = date_str.strftime('%Y-%m-%d')
                
            price = Price(
                open=float(row['开盘'] if '开盘' in stock_df.columns else row['open']),
                close=float(row['收盘'] if '收盘' in stock_df.columns else row['close']),
                high=float(row['最高'] if '最高' in stock_df.columns else row['high']),
                low=float(row['最低'] if '最低' in stock_df.columns else row['low']),
                volume=int(row['成交量'] if '成交量' in stock_df.columns else row['volume']),
                time=date_str
            )
            prices.append(price)
        
        if not prices:
            return []
        
        # 按日期排序
        prices.sort(key=lambda x: x.time)
        
        # Cache the results as dicts
        _cache.set_prices(ticker, [p.model_dump() for p in prices])
        return prices
    except Exception as e:
        print(f"Error fetching price data for {ticker}: {str(e)}")
        return []


def get_financial_metrics(
    ticker: str,
    end_date: str,
    period: str = "ttm",
    limit: int = 10,
) -> list[FinancialMetrics]:
    """Fetch financial metrics from cache or API using AKShare."""
    # Check cache first
    if cached_data := _cache.get_financial_metrics(ticker):
        # Filter cached data by date and limit
        filtered_data = [FinancialMetrics(**metric) for metric in cached_data if metric["report_period"] <= end_date]
        filtered_data.sort(key=lambda x: x.report_period, reverse=True)
        if filtered_data:
            return filtered_data[:limit]

    # If not in cache or insufficient data, fetch from AKShare API
    try:
        # 确保end_date是字符串格式
        if isinstance(end_date, datetime.date):
            end_date = end_date.strftime('%Y-%m-%d')
            
        # 获取股票基本财务指标
        # 使用akshare的stock_financial_analysis_indicator函数获取财务指标
        fin_df = ak.stock_financial_analysis_indicator(symbol=ticker, start_year="2000")
        leg_indicator_df = ak.stock_value_em(symbol=ticker)
        
        # 获取市值数据
        market_cap = get_market_cap(ticker, end_date)
        
        # 字段映射定义（英文字段 -> 可能的中文字段列表）
        field_mappings = {
            "price_to_earnings_ratio": ["市盈率", "市盈率(动态)", "市盈率(静态)", "pe", "PE(TTM)"],
            "price_to_book_ratio": ["市净率", "pb"],
            "price_to_sales_ratio": ["市销率", "ps"],
            "gross_margin": ["销售毛利率(%)", "毛利率", "毛利率(%)"],
            "operating_margin": ["营业利润率", "营业利润率(%)"],
            "net_margin": ["销售净利率(%)", "净利率", "净利率(%)"],
            "return_on_equity": ["净资产收益率(%)", "加权净资产收益率(%)", "净资产收益率"],
            "return_on_assets": ["总资产利润率(%)", "总资产净利润率(%)", "总资产报酬率", "总资产报酬率(%)"],
            "return_on_invested_capital": ["资本回报率"],
            "asset_turnover": ["总资产周转率(次)", "总资产周转率"],
            "inventory_turnover": ["存货周转率(次)", "存货周转率"],
            "receivables_turnover": ["应收账款周转率(次)", "应收账款周转率"],
            "days_sales_outstanding": ["应收账款周转天数(天)", "应收账款周转天数"],
            "operating_cycle": ["营业周期(天)", "营业周期"],
            "working_capital_turnover": ["营运资金周转率(次)", "营运资金周转率"],
            "current_ratio": ["流动比率"],
            "quick_ratio": ["速动比率"],
            "cash_ratio": ["现金比率(%)", "现金比率"],
            "operating_cash_flow_ratio": ["经营现金净流量与净利润的比率(%)", "现金流量比率"],
            "debt_to_equity": ["负债与所有者权益比率(%)", "产权比率"],
            "debt_to_assets": ["资产负债率(%)", "资产负债率"],
            "interest_coverage": ["利息支付倍数", "利息保障倍数"],
            "revenue_growth": ["主营业务收入增长率(%)", "营业收入增长率(%)"],
            "earnings_growth": ["净利润增长率(%)", "净利润增长率"],
            "book_value_growth": ["净资产增长率(%)", "净资产增长率"],
            "earnings_per_share_growth": ["每股收益增长率", "每股收益增长率(%)"],
            "free_cash_flow_growth": ["自由现金流增长率", "自由现金流增长率(%)"],
            "operating_income_growth": ["营业利润增长率", "营业利润增长率(%)"],
            "ebitda_growth": ["EBITDA增长率", "EBITDA增长率(%)"],
            "payout_ratio": ["股息发放率(%)", "股息率(%)", "派息率(%)"],
            "earnings_per_share": ["每股收益", "加权每股收益(元)", "基本每股收益(元)", "每股收益_调整后(元)"],
            "book_value_per_share": ["每股净资产", "每股净资产_调整前(元)", "每股净资产_调整后(元)"],
            "free_cash_flow_per_share": ["每股经营性现金流(元)", "每股现金流"]
        }
        
        # 将数据转换为FinancialMetrics对象列表
        financial_metrics = []
        for _, row in fin_df.iterrows():
            report_date = row['日期'] if '日期' in fin_df.columns else str(row['报告期'])
            # 确保report_date和end_date都是字符串格式
            if isinstance(report_date, pd.Timestamp) or isinstance(report_date, datetime.date):
                report_date = report_date.strftime('%Y-%m-%d')
                
            if report_date > end_date:
                continue
            
            # 创建基础FinancialMetrics对象，所有字段都设置默认值为None
            metrics_dict = {
                "ticker": ticker,
                "report_period": report_date,
                "period": period,
                "currency": "CNY",
                "market_cap": market_cap,
                "enterprise_value": None,
                "price_to_earnings_ratio": None,
                "price_to_book_ratio": None,
                "price_to_sales_ratio": None,
                "enterprise_value_to_ebitda_ratio": None,
                "enterprise_value_to_revenue_ratio": None,
                "free_cash_flow_yield": None,
                "peg_ratio": None,
                "gross_margin": None,
                "operating_margin": None,
                "net_margin": None,
                "return_on_equity": None,
                "return_on_assets": None,
                "return_on_invested_capital": None,
                "asset_turnover": None,
                "inventory_turnover": None,
                "receivables_turnover": None,
                "days_sales_outstanding": None,
                "operating_cycle": None,
                "working_capital_turnover": None,
                "current_ratio": None,
                "quick_ratio": None,
                "cash_ratio": None,
                "operating_cash_flow_ratio": None,
                "debt_to_equity": None,
                "debt_to_assets": None,
                "interest_coverage": None,
                "revenue_growth": None,
                "earnings_growth": None,
                "book_value_growth": None,
                "earnings_per_share_growth": None,
                "free_cash_flow_growth": None,
                "operating_income_growth": None,
                "ebitda_growth": None,
                "payout_ratio": None,
                "earnings_per_share": None,
                "book_value_per_share": None,
                "free_cash_flow_per_share": None
            }
            
            # 使用字段映射填充字段值 - 从fin_df获取
            for eng_field, cn_fields in field_mappings.items():
                for cn_field in cn_fields:
                    if cn_field in fin_df.columns and not pd.isna(row[cn_field]):
                        try:
                            metrics_dict[eng_field] = float(row[cn_field])
                            break  # 找到并设置了值，跳出内循环
                        except (ValueError, TypeError):
                            continue  # 无法转换为浮点数，尝试下一个字段
            
            # 处理leg_indicator_df数据 - 将其指标也合并到metrics中
            if leg_indicator_df is not None and not leg_indicator_df.empty:
                # 寻找与当前报告期最接近的记录
                if 'trade_date' in leg_indicator_df.columns:
                    # 查找日期最接近的记录
                    leg_report_dates = pd.to_datetime(leg_indicator_df['trade_date'], errors='coerce')
                    curr_report_date = pd.to_datetime(report_date, errors='coerce')
                    if not pd.isna(curr_report_date):
                        # 计算日期差值并找到最近的记录
                        date_diff = abs(leg_report_dates - curr_report_date)
                        closest_idx = date_diff.argmin()
                        leg_row = leg_indicator_df.iloc[closest_idx]
                        
                        # 使用相同的字段映射更新指标
                        for eng_field, cn_fields in field_mappings.items():
                            # 如果该字段已有值，则跳过
                            if metrics_dict[eng_field] is not None:
                                continue
                                
                            for cn_field in cn_fields:
                                if cn_field in leg_indicator_df.columns and not pd.isna(leg_row[cn_field]):
                                    try:
                                        metrics_dict[eng_field] = float(leg_row[cn_field])
                                        break  # 找到并设置了值，跳出内循环
                                    except (ValueError, TypeError):
                                        continue  # 无法转换为浮点数，尝试下一个字段
            
            # 创建FinancialMetrics对象并添加到列表
            try:
                metrics = FinancialMetrics(**metrics_dict)
                financial_metrics.append(metrics)
            except Exception as e:
                print(f"创建FinancialMetrics对象失败: {str(e)}")
                print(f"错误的数据: {metrics_dict}")
        
        # 限制返回数量
        financial_metrics.sort(key=lambda x: x.report_period, reverse=True)
        financial_metrics = financial_metrics[:limit]
        
        if not financial_metrics:
            return []
        
        # Cache the results as dicts
        _cache.set_financial_metrics(ticker, [m.model_dump() for m in financial_metrics])
        return financial_metrics
    except Exception as e:
        print(f"Error fetching financial metrics for {ticker}: {str(e)}")
        return []

def determine_exchange(stock_code: str) -> str:
        """
        根据股票代码判断所属交易所
        :param stock_code: 纯数字格式的股票代码，如"000001"
        :return: 交易所代码，如"SH"或"SZ"
        """
        # 如果已经包含交易所信息，直接提取
        if "." in stock_code:
            exchange = stock_code.split(".")[1]
            if exchange in ["SH", "SZ", "BJ"]:
                return exchange
        
        # 根据首位数字判断交易所
        # 上海证券交易所
        if stock_code.startswith("6"):
            return "SH"
        # 深圳证券交易所
        elif stock_code.startswith("0") or stock_code.startswith("3"):
            return "SZ"
        # 北京证券交易所
        elif stock_code.startswith("8") or stock_code.startswith("4"):
            return "BJ"
        else:
            return ""

def search_line_items(
    ticker: str,
    line_items: list[str],  # List of English financial term keys (e.g., 'revenue', 'net_income') to include. If empty, all mappable items are included.
    end_date: str,
    period: str = "ttm",
    limit: int = 10,
) -> list[LineItem]:
    """Fetch line items from AKShare API, primarily using Sina Finance source."""
    try:
        original_ticker = ticker
        
        pure_code = "".join([c for c in ticker if c.isdigit()])[:6]
        if not pure_code:
            print(f"无效的股票代码: {ticker}")
            return []
            
        exchange = determine_exchange(pure_code)
        if not exchange:
            print(f"无法确定股票代码 {pure_code} 的交易所，尝试默认处理。")
            # Defaulting or specific handling if exchange is unknown might be needed for some APIs
            # For Sina, it generally requires prefix like 'sh', 'sz'
            # However, ak.stock_financial_report_sina seems to handle pure codes or prefixed codes for some cases.
            # For robustness, we construct it. If determine_exchange fails, this might be an issue.
            # If pure_code is e.g. "000001", formatted_ticker would be "000001"
            # If pure_code is "600519", formatted_ticker would be "600519"
            # Let's ensure formatted_ticker for Sina is sh/sz prefixed
            if pure_code.startswith("6"):
                 formatted_ticker = f"SH{pure_code}"
            elif pure_code.startswith("0") or pure_code.startswith("3"):
                 formatted_ticker = f"SZ{pure_code}"
            elif pure_code.startswith("8") or pure_code.startswith("4"):
                 formatted_ticker = f"BJ{pure_code}" # Beijing Stock Exchange
            else:
                # Fallback or error if prefix cannot be determined
                print(f"无法为代码 {pure_code} 生成带交易所前缀的股票代码，Sina API 可能失败。")
                formatted_ticker = pure_code # try with pure code if exchange is ambiguous
        else:
            formatted_ticker = f"{exchange}{pure_code}"

        # print(f"处理股票: {formatted_ticker} (原始代码: {ticker}) 的财报项目搜索")
        
        if isinstance(end_date, datetime.date):
            end_date_str = end_date.strftime('%Y-%m-%d')
        else:
            end_date_str = end_date # Assume already "YYYY-MM-DD" string

        balance_df, income_df, cashflow_df = None, None, None
        
        try:
            # print(f"尝试新浪财经API获取财务报表 (代码: {formatted_ticker})...")
            # balance_df = ak.stock_financial_report_sina(stock=formatted_ticker, symbol="资产负债表")
            # income_df = ak.stock_financial_report_sina(stock=formatted_ticker, symbol="利润表")
            # cashflow_df = ak.stock_financial_report_sina(stock=formatted_ticker, symbol="现金流量表")
            
            cashflow_df = ak.stock_cash_flow_sheet_by_report_em(symbol=formatted_ticker)
            income_df = ak.stock_profit_sheet_by_yearly_em(symbol=formatted_ticker)
            balance_df = ak.stock_balance_sheet_by_report_em(symbol=formatted_ticker)
            
            # print(f"新浪API - 资产负债表: {'成功获取' if balance_df is not None and not balance_df.empty else '未获取或为空'}")
            # print(f"新浪API - 利润表: {'成功获取' if income_df is not None and not income_df.empty else '未获取或为空'}")
            # print(f"新浪API - 现金流量表: {'成功获取' if cashflow_df is not None and not cashflow_df.empty else '未获取或为空'}")

        except Exception as e:
            print(f"调用新浪财经API (ak.stock_financial_report_sina) 时发生错误: {str(e)}")
            # If API call itself fails, return empty
            return []

        if (balance_df is None or balance_df.empty) and \
           (income_df is None or income_df.empty) and \
           (cashflow_df is None or cashflow_df.empty):
            print(f"未能从新浪财经获取到 {formatted_ticker} 的任何财务报表数据。")
            return []
                
        all_line_item_objects = []
        aggregated_data_by_date = {}

        # 1. 收集所有唯一的、有效的报告日期，并确保它们在 end_date_str 之前或当天
        unique_valid_report_dates = set()
        for report_name_for_dates, df_for_dates in {'资产负债表': balance_df, '利润表': income_df, '现金流量表': cashflow_df}.items():
            if df_for_dates is None or df_for_dates.empty or 'REPORT_DATE' not in df_for_dates.columns:
                continue
            for raw_report_date in df_for_dates['REPORT_DATE'].astype(str):
                try:
                    parsed_date = pd.to_datetime(raw_report_date.strip(), format='%Y%m%d')
                    date_str = parsed_date.strftime('%Y-%m-%d')
                    if date_str <= end_date_str:
                        unique_valid_report_dates.add(date_str)
                except ValueError:
                    try: # Fallback parsing
                        parsed_date = pd.to_datetime(raw_report_date.strip())
                        date_str = parsed_date.strftime('%Y-%m-%d')
                        if date_str <= end_date_str:
                           unique_valid_report_dates.add(date_str)
                    except ValueError:
                        # print(f"[诊断] 初始日期收集：无法解析日期 '{raw_report_date}' 从报表 '{report_name_for_dates}'")
                        pass # Ignore invalid date formats during initial collection
        
        # 将收集到的日期排序，通常我们希望从最近的开始处理或返回
        sorted_unique_dates = sorted(list(unique_valid_report_dates), reverse=True)

        #print(f"[诊断] 识别出的有效且排序后的唯一报告日期 (<= {end_date_str}): {sorted_unique_dates[:limit*2]}... (总计: {len(sorted_unique_dates)})")

        # 2. 按日期聚合数据
        for current_report_date_str in sorted_unique_dates: # Iterate over unique, sorted dates
            # 初始化当前报告日期的聚合数据字典
            if current_report_date_str not in aggregated_data_by_date:
                aggregated_data_by_date[current_report_date_str] = {
                    "ticker": original_ticker,
                    "report_period": current_report_date_str,
                    "period": period, 
                    "currency": "CNY"
                }
            
            has_any_mapped_data_for_this_date = False

            # 依次处理资产负债表、利润表和现金流量表
            for report_name, df_original in {'资产负债表': balance_df, '利润表': income_df, '现金流量表': cashflow_df}.items():
                if df_original is None or df_original.empty or 'REPORT_DATE' not in df_original.columns:
                    # print(f"[诊断] 聚合处理中，报表 '{report_name}' 为空或无'报告日'列，跳过。")
                    continue
                
                # 找到当前报告日期在当前报表df_original中的对应行
                # 需要将df_original中的'报告日'列转换为与current_report_date_str相同的格式进行匹配
                # 创建一个临时列用于安全匹配，避免修改原始df的'报告日'数据类型
                try:
                    # Attempt to create a comparable date string series from df_original['报告日']
                    df_original_report_dates_as_str = df_original['REPORT_DATE'].astype(str).str.strip().apply(
                        lambda x: pd.to_datetime(x, format='%Y%m%d').strftime('%Y-%m-%d') if pd.notna(x) and len(x)==8 and x.isdigit() 
                        else (pd.to_datetime(x).strftime('%Y-%m-%d') if pd.notna(x) else None)
                    )
                    relevant_row_series = df_original[df_original_report_dates_as_str == current_report_date_str]
                except Exception as e_date_conv_inner:
                    print(f"[诊断] 内部日期转换错误，报表: {report_name}, 日期: {current_report_date_str}, 错误: {e_date_conv_inner}")
                    relevant_row_series = pd.DataFrame() # Empty DataFrame if conversion fails

                if relevant_row_series.empty:
                    # print(f"[诊断] 报表 '{report_name}' 中未找到日期为 '{current_report_date_str}' 的数据行。")
                    continue
                
                row_data = relevant_row_series.iloc[0] #应该只有一行匹配
                # print(f"[诊断] 处理报表 '{report_name}' 中日期为 '{current_report_date_str}' 的行。")

                # 财务项目的列名是 df_original.columns 中排除了 '报告日' 和其他元数据列的部分
                metadata_column_names = ['数据源', '是否审计', '公告日期', '币种', '类型', '更新日期']
                financial_item_column_names = [
                    col for col in df_original.columns 
                    if col != 'REPORT_DATE' and col not in metadata_column_names
                ]

                if not financial_item_column_names:
                    # print(f"[诊断] 报表 '{report_name}' (针对日期 {current_report_date_str}) 未找到可识别的财务项目列。")
                    continue

                for original_col_name in financial_item_column_names:
                    stripped_col_name = original_col_name.strip()
                    item_value = row_data.get(original_col_name) # Use .get() for safety

                    if pd.isna(item_value) or str(item_value).strip() == '--' or str(item_value).strip() == '':
                        continue 

                    english_term = finance_terms_mapping.get(stripped_col_name)
                    
                    if english_term:
                        if line_items and english_term not in line_items:
                            # print(f"[诊断] 映射得到的英文术语 '{english_term}' (来自中文列: '{stripped_col_name}') 因不在请求的 line_items ({line_items}) 英文键列表中而被跳过。")
                            continue
                        try:
                            numeric_value = float(str(item_value).replace(',', ''))
                            # 添加到对应日期的聚合数据字典中
                            aggregated_data_by_date[current_report_date_str][english_term] = numeric_value
                            has_any_mapped_data_for_this_date = True 

                            # If the mapped term is total_liabilities, also add total_debt with the same value
                            if english_term == "total_liabilities":
                                aggregated_data_by_date[current_report_date_str]["total_debt"] = numeric_value
                                # print(f"[诊断] {current_report_date_str} - {report_name}: 同时设置了 'total_debt' = {numeric_value} (基于 total_liabilities)")

                            # print(f"[诊断] {current_report_date_str} - {report_name}: 成功映射并设置 '{english_term}' = {numeric_value}")
                        except ValueError:
                            print(f"[诊断] 警告: 无法将财务项目 '{stripped_col_name}' (原始列名: '{original_col_name}') 的值 '{item_value}' (日期: {current_report_date_str}) 转换为数字。")
                        except Exception as e_val_conv_agg:
                            print(f"[诊断] 错误: 聚合转换值 '{item_value}' (项目: '{stripped_col_name}') 时发生意外: {e_val_conv_agg}")
                    # else:
                        # print(f"[诊断] 中文列 '{stripped_col_name}' (来自报表 {report_name}) 未在 finance_terms_mapping 中找到映射。")
            
            # 单个日期处理完毕，检查是否有数据
            current_date_dict = aggregated_data_by_date[current_report_date_str]
            if not has_any_mapped_data_for_this_date or len(current_date_dict) <= 4: # 基础字段有4个
                # print(f"[诊断] 日期 {current_report_date_str}: 没有成功映射任何数据项或数据不足。移除此日期。")
                del aggregated_data_by_date[current_report_date_str] # 移除没有实际财务数据的条目
            # else:
                # print(f"[诊断] 日期 {current_report_date_str}: 完成数据聚合, 包含 {len(current_date_dict)-4} 个财务数据点。 数据: {current_date_dict}")

        # 3. 创建LineItem对象
        # print(f"[诊断] 开始从聚合数据创建 LineItem 对象。聚合字典大小: {len(aggregated_data_by_date)}")
        for report_date_key, data_dict in aggregated_data_by_date.items():
            if len(data_dict) > 4: # 确保除了基础字段外，还有其他财务数据
                try:
                    line_item_obj = LineItem(**data_dict)
                    all_line_item_objects.append(line_item_obj)
                    # print(f"[诊断] 成功为日期 {report_date_key} 创建 LineItem 对象。")
                except Exception as e_create_final:
                    print(f"[诊断] 创建最终 LineItem 对象失败 (日期: {report_date_key}): {str(e_create_final)}. 数据: {data_dict}")
            # else:
                # print(f"[诊断] 跳过为日期 {report_date_key} 创建 LineItem 对象，因数据不足。")

        # 4. 排序和限制 (已按日期降序处理，此处主要是应用 limit)
        # all_line_item_objects.sort(key=lambda x: x.report_period, reverse=True) # 理论上已排序
        final_results = all_line_item_objects[:limit] # 应用limit
        
        #print(f"总共找到并处理了 {len(final_results)}/{len(all_line_item_objects)} 个财报项目记录 (已应用 limit: {limit})。原始聚合日期数: {len(aggregated_data_by_date)}")
        return final_results

    except Exception as e:
        print(f"搜索财报项目时发生严重错误 (ticker: {ticker}): {str(e)}")
        import traceback
        traceback.print_exc()
        return []


def get_insider_trades(
    ticker: str,
    end_date: str,
    start_date: str | None = None,
    limit: int = 1000,
) -> list[InsiderTrade]:
    """
    Fetch insider trading data using ak.stock_management_change_ths.
    Parses the specific DataFrame structure returned by this API.
    Filters by date range and applies a limit.
    """
    
    # Determine actual start_date if not provided
    if start_date is None:
        try:
            end_date_obj = datetime.datetime.strptime(end_date, "%Y-%m-%d")
            start_date_obj = end_date_obj - datetime.timedelta(days=2*365) # Default 2-year lookback
            actual_start_date = start_date_obj.strftime("%Y-%m-%d")
        except (ValueError, TypeError) as e:
            print(f"[get_insider_trades] Error parsing end_date '{end_date}\'. Defaulting start_date to 2 years ago from today. Error: {e}")
            today = datetime.date.today()
            actual_start_date = (today - datetime.timedelta(days=2*365)).strftime("%Y-%m-%d")
            # If end_date was also problematic, this might need further thought, but current signature requires end_date
    else:
        actual_start_date = start_date

    # print(f"获取高管持股变动数据 - 股票: {ticker} (日期范围: {actual_start_date} 至 {end_date}, 限制: {limit})")
    insider_trades_list = []
    original_ticker = ticker 

    try:
        management_change_df = ak.stock_management_change_ths(symbol=original_ticker)
        
        if management_change_df is not None and not management_change_df.empty:
            # print(f"[诊断] stock_management_change_ths 为 {original_ticker} 返回了 {len(management_change_df)} 条记录。")

            for _, row in management_change_df.iterrows():
                try:
                    # '变动日期' can be datetime.date object from akshare, convert to string
                    raw_trade_date = row['变动日期']
                    if isinstance(raw_trade_date, datetime.date):
                        trade_date_str = raw_trade_date.strftime('%Y-%m-%d')
                    else:
                        trade_date_str = str(raw_trade_date).strip()
                    
                    # Date filtering
                    if trade_date_str < actual_start_date:
                        continue
                    if trade_date_str > end_date: # New filter based on end_date
                        continue

                    person_name = str(row['变动人']).strip()
                    position = str(row['与公司高管关系']).strip()
                    
                    # Parse '变动数量' which contains text like "增持700.00" or "减持700.00"
                    change_quantity_str = str(row['变动数量']).strip()
                    transaction_shares_val = None
                    transaction_type_val = None

                    # Helper function to parse numbers with '万'
                    def parse_share_value(value_str):
                        value_str = str(value_str).strip()
                        if not value_str or value_str == '--':
                            return None
                        multiplier = 1
                        if '万' in value_str:
                            multiplier = 10000
                            value_str = value_str.replace('万', '')
                        try:
                            return float(value_str) * multiplier
                        except ValueError:
                            return None

                    if "增持" in change_quantity_str:
                        transaction_type_val = "buy"
                        numeric_part_str = change_quantity_str.replace("增持", "").strip()
                        transaction_shares_val = parse_share_value(numeric_part_str)
                    elif "减持" in change_quantity_str:
                        transaction_type_val = "sell"
                        numeric_part_str = change_quantity_str.replace("减持", "").strip()
                        transaction_shares_val = parse_share_value(numeric_part_str)
                    else:
                        # Attempt to infer from sign if it's just a number (though sample shows text)
                        # This part might be less relevant if '增持'/'减持' is always present
                        parsed_val_direct = parse_share_value(change_quantity_str)
                        if parsed_val_direct is not None:
                            if parsed_val_direct > 0:
                                transaction_type_val = "buy"
                                transaction_shares_val = parsed_val_direct
                            elif parsed_val_direct < 0:
                                transaction_type_val = "sell"
                                transaction_shares_val = abs(parsed_val_direct)
                            else: # 0 change, skip
                                print(f"[诊断] '变动数量' 为0: {change_quantity_str}，跳过此行。")
                                continue
                        else:
                            print(f"[诊断] 无法解析 '变动数量': {change_quantity_str}，跳过此行。")
                            continue
                    
                    if transaction_shares_val is None or transaction_type_val is None:
                        print(f"[诊断] 关键信息缺失 (股份或类型) 从 '{change_quantity_str}', 跳过.")
                        continue

                    avg_price_str = str(row['交易均价']).strip()
                    avg_price = float(avg_price_str) if avg_price_str and avg_price_str != '--' else None
                    
                    shares_after_str = str(row['剩余股数']).strip()
                    shares_after_trade = parse_share_value(shares_after_str)

                    transaction_value_val = None
                    if transaction_shares_val is not None and avg_price is not None:
                        transaction_value_val = transaction_shares_val * avg_price

                    # shares_owned_before_transaction can be calculated if needed
                    # shares_owned_before = None
                    # if shares_after_trade is not None and transaction_shares_val is not None:
                    #     if transaction_type_val == 'buy':
                    #         shares_owned_before = shares_after_trade - transaction_shares_val
                    #     elif transaction_type_val == 'sell':
                    #         shares_owned_before = shares_after_trade + transaction_shares_val
                    
                    insider_trade_obj = InsiderTrade(
                        ticker=original_ticker,
                        issuer=original_ticker, # Defaulting issuer to ticker
                        name=person_name,
                        title=position,
                        is_board_director=None, # Cannot determine from source
                        transaction_date=trade_date_str,
                        transaction_shares=transaction_shares_val,
                        transaction_type=transaction_type_val,
                        transaction_price_per_share=avg_price,
                        transaction_value=transaction_value_val,
                        shares_owned_before_transaction=None, # Placeholder, can be calculated
                        shares_owned_after_transaction=shares_after_trade,
                        security_title="股票", # Default
                        filing_date=None # Not available from this source
                    )
                    insider_trades_list.append(insider_trade_obj)

                except Exception as e_row:
                    print(f"[诊断] 处理行数据时出错: {row.to_dict()}, 错误: {e_row}")
                    continue
            
            # Sort by date descending before returning
            insider_trades_list.sort(key=lambda x: x.transaction_date, reverse=True)
            
            # Apply limit
            if limit > 0 and len(insider_trades_list) > limit:
                insider_trades_list = insider_trades_list[:limit]

        else:
            print(f"stock_management_change_ths 为 {original_ticker} 返回了空DataFrame或None。")

    except Exception as e:
        print(f"调用 stock_management_change_ths (股票: {original_ticker}) 时发生错误: {e}")
        import traceback
        traceback.print_exc()


    if not insider_trades_list:
        print(f"最终未能为 {original_ticker} (开始日期: {actual_start_date}) 收集到任何高管持股变动数据。")
    # else:
        # print(f"为 {original_ticker} 成功收集到 {len(insider_trades_list)} 条高管持股变动数据 (已应用日期过滤和限制)。")

    return insider_trades_list


def get_company_news(
    ticker: str,
    end_date: str,
    start_date: str | None = None,
    limit: int = 1000,
) -> list[CompanyNews]:
    """Fetch company news from cache or AKShare API."""
    # Check cache first
    if cached_data := _cache.get_company_news(ticker):
        # Filter cached data by date range
        filtered_data = [CompanyNews(**news) for news in cached_data if (start_date is None or news["date"] >= start_date) and news["date"] <= end_date]
        filtered_data.sort(key=lambda x: x.date, reverse=True)
        if filtered_data:
            return filtered_data

    # If not in cache or insufficient data, fetch from AKShare API
    try:
        # 获取股票新闻
        news_df = ak.stock_news_em(symbol=ticker)
        
        all_news = []
        if news_df is not None and not news_df.empty:
            for _, row in news_df.iterrows():
                news_date = row['新闻时间'] if '新闻时间' in news_df.columns else row['时间'] if '时间' in news_df.columns else end_date
                
                # 确保日期为字符串格式
                if isinstance(news_date, pd.Timestamp) or isinstance(news_date, datetime.date):
                    news_date = news_date.strftime('%Y-%m-%d')
                
                # 日期过滤 - 确保都是字符串类型再比较
                if isinstance(end_date, datetime.date):
                    end_date_str = end_date.strftime('%Y-%m-%d')
                else:
                    end_date_str = end_date
                    
                if news_date > end_date_str:
                    continue
                    
                if start_date:
                    if isinstance(start_date, datetime.date):
                        start_date_str = start_date.strftime('%Y-%m-%d')
                    else:
                        start_date_str = start_date
                        
                    if news_date < start_date_str:
                        continue
                    
                news = CompanyNews(
                    ticker=ticker,
                    title=row['新闻标题'] if '新闻标题' in news_df.columns else row['标题'] if '标题' in news_df.columns else "",
                    author="东方财富" if '新闻来源' not in news_df.columns else row['新闻来源'],
                    source="东方财富" if '新闻来源' not in news_df.columns else row['新闻来源'],
                    date=news_date,
                    url=row['新闻链接'] if '新闻链接' in news_df.columns else "",
                    sentiment=None,  # AKShare不提供情感分析
                )
                all_news.append(news)
        
        if not all_news:
            return []
            
        # 按日期排序
        all_news.sort(key=lambda x: x.date, reverse=True)
        
        # 限制数量
        all_news = all_news[:limit]

        # Cache the results
        _cache.set_company_news(ticker, [news.model_dump() for news in all_news])
        return all_news
    except Exception as e:
        print(f"Error fetching company news for {ticker}: {str(e)}")
        return []


def get_market_cap(
    ticker: str,
    end_date: str,
) -> float | None:
    """Fetch market cap from AKShare API."""
    # 确保end_date是字符串格式
    if isinstance(end_date, datetime.date):
        end_date = end_date.strftime('%Y-%m-%d')
    
    # 尝试多种方式获取市值数据
    try:
        #print(f"尝试获取{ticker}的市值数据...")
        
        # 方法1: 使用stock_individual_info_em
        try:
            # 获取股票实时行情
            stock_info_df = ak.stock_individual_info_em(symbol=ticker)
            if stock_info_df is not None and not stock_info_df.empty:
                if 'item' in stock_info_df.columns and 'value' in stock_info_df.columns:
                    for _, row in stock_info_df.iterrows():
                        if row['item'] == '总市值' or row['item'] == '市值':
                            try:
                                # 处理格式化的数字（如带逗号的数字）
                                value_str = str(row['value'])
                                # 检查是否包含单位如"亿"
                                if '亿' in value_str:
                                    value_str = value_str.replace('亿', '').replace(',', '').strip()
                                    return float(value_str) * 100000000  # 转换亿为元
                                else:
                                    value_str = value_str.replace(',', '').strip()
                                    if '万' in value_str:
                                        value_str = value_str.replace('万', '').strip()
                                        return float(value_str) * 10000  # 转换万为元
                                    return float(value_str)
                            except (ValueError, TypeError) as e:
                                print(f"处理市值数据失败: {e}")
        except Exception as e:
            print(f"方法1获取市值失败: {e}")
            
        # 方法2: 使用stock_zh_a_spot_em
        try:
            # print("尝试方法2获取市值...")
            spot_df = ak.stock_zh_a_spot_em()
            if spot_df is not None and not spot_df.empty:
                if '代码' in spot_df.columns and '总市值' in spot_df.columns:
                    ticker_row = spot_df[spot_df['代码'] == ticker]
                    if not ticker_row.empty and not pd.isna(ticker_row['总市值'].iloc[0]):
                        try:
                            # 股票行情API中的市值通常是以亿为单位
                            return float(ticker_row['总市值'].iloc[0])
                        except (ValueError, TypeError):
                            pass
        except Exception as e:
            print(f"方法2获取市值失败: {e}")
            
        # 方法3: 使用stock_profile_cninfo
        try:
            #print("尝试方法3获取市值...")
            ticker_code = ticker
            # 确保股票代码格式正确
            if ticker.startswith(('6', '5', '9')):
                ticker_code = f"SH{ticker}"
            elif ticker.startswith(('0', '3')):
                ticker_code = f"SZ{ticker}"
                
            stock_profile = ak.stock_profile_cninfo(symbol=ticker_code)
            if stock_profile is not None and not stock_profile.empty:
                market_cap_cols = ['总市值', '市值', '流通市值']
                for col in market_cap_cols:
                    if col in stock_profile.columns and not pd.isna(stock_profile[col].iloc[0]):
                        try:
                            value = stock_profile[col].iloc[0]
                            if isinstance(value, str):
                                if '亿' in value:
                                    value = float(value.replace('亿', '').strip()) * 100000000
                                elif '万' in value:
                                    value = float(value.replace('万', '').strip()) * 10000
                                else:
                                    value = float(value)
                            return value
                        except (ValueError, TypeError):
                            pass
        except Exception as e:
            print(f"方法3获取市值失败: {e}")
            
        # 方法4: 使用stock_zh_a_hist获取价格，然后用股本计算市值
        try:
            # print("尝试方法4计算市值...")
            # 获取最近的收盘价
            price_df = ak.stock_zh_a_hist(symbol=ticker, period="daily", 
                                       start_date=(datetime.datetime.now() - datetime.timedelta(days=7)).strftime('%Y%m%d'), 
                                       end_date=datetime.datetime.now().strftime('%Y%m%d'), 
                                       adjust="")
            
            if price_df is not None and not price_df.empty and '收盘' in price_df.columns:
                latest_price = float(price_df['收盘'].iloc[-1])
                
                # 获取股本数据
                share_df = ak.stock_share_change_cninfo(symbol=ticker)
                if share_df is not None and not share_df.empty:
                    share_cols = ['总股本', '变动后股本', '股本']
                    for col in share_cols:
                        if col in share_df.columns and not pd.isna(share_df[col].iloc[0]):
                            try:
                                shares = float(share_df[col].iloc[0])
                                return latest_price * shares
                            except (ValueError, TypeError):
                                pass
        except Exception as e:
            print(f"方法4计算市值失败: {e}")
            
        # 所有方法都失败
        # print(f"所有方法都无法获取{ticker}的市值数据")
        return None
    except Exception as e:
        print(f"获取市值数据时出现未知错误: {str(e)}")
        return None


def prices_to_df(prices: list[Price]) -> pd.DataFrame:
    """Convert prices to a DataFrame."""
    df = pd.DataFrame([p.model_dump() for p in prices])
    df["Date"] = pd.to_datetime(df["time"])
    df.set_index("Date", inplace=True)
    numeric_cols = ["open", "close", "high", "low", "volume"]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df.sort_index(inplace=True)
    return df


# Update the get_price_data function to use the new functions
def get_price_data(ticker: str, start_date: str, end_date: str) -> pd.DataFrame:
    prices = get_prices(ticker, start_date, end_date)
    return prices_to_df(prices)


# 测试所有API数据获取函数的main方法
if __name__ == "__main__":
    import sys
    from tabulate import tabulate
    from pprint import pprint
    
    # 默认测试股票代码和日期
    ticker = "600519"  # 贵州茅台
    end_date = datetime.datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.datetime.now() - datetime.timedelta(days=365)).strftime("%Y-%m-%d")
    
    # 如果命令行参数提供了股票代码，则使用命令行参数
    if len(sys.argv) > 1:
        ticker = sys.argv[1]
    
    print(f"测试API数据获取函数，测试股票: {ticker}, 开始日期: {start_date}, 结束日期: {end_date}")
    
    # 测试获取价格数据
    print("\n1. 测试 get_prices 函数:")
    try:
        prices = get_prices(ticker, start_date, end_date)
        if prices:
            prices_df = pd.DataFrame([p.model_dump() for p in prices[:5]])
            print(f"成功获取 {len(prices)} 条价格数据，显示前5条:")
            print(tabulate(prices_df, headers="keys", tablefmt="grid"))
        else:
            print("未获取到价格数据")
    except Exception as e:
        print(f"获取价格数据时出错: {str(e)}")
    
    # 测试获取财务指标
    print("\n2. 测试 get_financial_metrics 函数:")
    try:
        metrics = get_financial_metrics(ticker, end_date)
        if metrics:
            metrics_df = pd.DataFrame([{
                'report_period': m.report_period,
                'price_to_earnings_ratio': m.price_to_earnings_ratio,
                'price_to_book_ratio': m.price_to_book_ratio,
                'return_on_equity': m.return_on_equity,
                'debt_to_equity': m.debt_to_equity,
                'earnings_per_share': m.earnings_per_share
            } for m in metrics[:3]])
            print(f"成功获取 {len(metrics)} 组财务指标，显示前3组核心指标:")
            print(tabulate(metrics_df, headers="keys", tablefmt="grid"))
        else:
            print("未获取到财务指标数据")
    except Exception as e:
        print(f"获取财务指标时出错: {str(e)}")
    
    # 测试获取财务报表项目
    print("\n3. 测试 search_line_items 函数:")
    try:
        line_items_param = [
                "free_cash_flow",
                "ebit",
                "interest_expense",
                "capital_expenditure",
                # "depreciation_and_amortization", # Ensure this key exists in finance_terms_mapping if uncommented
                # "outstanding_shares",           # Ensure this key exists in finance_terms_mapping if uncommented
                "net_income",
                "total_liabilities",
                 "revenue", # Added for more test coverage
                 "operating_income",
                 "shareholders_equity"
            ]
        line_items_result = search_line_items(ticker, line_items_param, end_date, limit=50) # Fetching up to 5 report periods
        
        if line_items_result:
            print(f"成功从 search_line_items 获取到 {len(line_items_result)} 个 LineItem 对象。")
            print("详细数据如下 (最多显示前5个报告期):")
            
            display_count = 0
            for item in line_items_result:
                if display_count >= 50: # Limit the number of detailed items printed
                    print("...更多数据未显示...")
                    break
                
                item_dict = item.model_dump() 
                print(f"\n--- 报告期: {item.report_period}, Ticker: {item.ticker} ---")
                
                financial_data_points = {}
                for key, value in item_dict.items():
                    if key not in ['ticker', 'report_period', 'period', 'currency']:
                        financial_data_points[key] = value
                
                if financial_data_points:
                    # For better readability, print key-value pairs
                    for fin_key, fin_value in financial_data_points.items():
                        print(f"    {fin_key}: {fin_value}")
                else:
                    print("    此报告期没有提取到额外的财务数据点。")
                display_count += 1
        else:
            print("search_line_items 未返回任何财务报表项目数据。")
    except Exception as e:
        print(f"获取财务报表项目时出错: {str(e)}")
    
    # 测试获取内部人交易
    print("\n4. 测试 get_insider_trades 函数:")
    try:
        # 使用一个更早的开始日期来测试旧数据的处理
        insider_test_start_date = "2017-01-01"
        # end_date is already defined for the test script
        print(f"(测试 get_insider_trades 日期范围: {insider_test_start_date} 至 {end_date}, 限制: 10)")
        trades = get_insider_trades(ticker, end_date=end_date, start_date=insider_test_start_date, limit=10)
        if trades:
            trades_df = pd.DataFrame([{
                'transaction_date': t.transaction_date,
                'name': t.name,
                'title': t.title,
                'transaction_type': t.transaction_type,
                'transaction_shares': t.transaction_shares,
                'transaction_price_per_share': t.transaction_price_per_share
            } for t in trades[:5]])
            print(f"成功获取 {len(trades)} 条内部人交易记录，显示前5条:")
            print(tabulate(trades_df, headers="keys", tablefmt="grid"))
        else:
            print("未获取到内部人交易数据")
    except Exception as e:
        print(f"获取内部人交易数据时出错: {str(e)}")
    
    # 测试获取新闻
    print("\n5. 测试 get_company_news 函数:")
    try:
        news = get_company_news(ticker, end_date, start_date)
        if news:
            news_df = pd.DataFrame([{
                'date': n.date,
                'title': n.title[:50] + ('...' if len(n.title) > 50 else ''),
                'source': n.source
            } for n in news[:5]])
            print(f"成功获取 {len(news)} 条新闻，显示前5条:")
            print(tabulate(news_df, headers="keys", tablefmt="grid"))
        else:
            print("未获取到新闻数据")
    except Exception as e:
        print(f"获取新闻数据时出错: {str(e)}")
    
    # 测试获取市值
    print("\n6. 测试 get_market_cap 函数:")
    try:
        market_cap = get_market_cap(ticker, end_date)
        if market_cap:
            print(f"成功获取市值数据: {market_cap:,.2f} 元")
        else:
            print("未获取到市值数据")
    except Exception as e:
        print(f"获取市值数据时出错: {str(e)}")
    
    print("\n测试完成!")
