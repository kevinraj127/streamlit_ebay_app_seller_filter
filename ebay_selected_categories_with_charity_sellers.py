import streamlit as st
import requests
import pandas as pd
import datetime
import pytz
import plotly.express as px
import plotly.graph_objects as go
from base64 import b64encode
import json
import urllib.parse
import os
import warnings


# Initialize session state for saved searches
if 'saved_searches' not in st.session_state:
    st.session_state.saved_searches = []

# eBay API credentials
CLIENT_ID = st.secrets["ebay"]["CLIENT_ID"]
CLIENT_SECRET = st.secrets["ebay"]["CLIENT_SECRET"]

# Encode credentials
credentials = b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()

# Get OAuth2 token
@st.cache_data(ttl=3600)
def get_access_token():
    token_url = "https://api.ebay.com/identity/v1/oauth2/token"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": f"Basic {credentials}"
    }
    data = {
        "grant_type": "client_credentials",
        "scope": "https://api.ebay.com/oauth/api_scope"
    }
    response = requests.post(token_url, headers=headers, data=data)
    return response.json().get("access_token")

access_token = get_access_token()

# Seller categorization function
def categorize_seller(feedback_score, feedback_percent):
    try:
        score = int(feedback_score) if feedback_score is not None else 0
        percent = float(feedback_percent) if feedback_percent is not None else 0
    except (ValueError, TypeError):
        return "Uncategorized"
    
    if score >= 5000 and percent >= 99:
        return "Elite"
    elif score >= 1000 and percent >= 98:
        return "Excellent"
    elif score >= 500 and percent >= 97:
        return "Very Good"
    elif score >= 100 and percent >= 95:
        return "Good"
    elif score >= 100 and percent >= 90:
        return "Average"
    elif score < 100 and percent >= 90:
        return "Inexperienced"
    elif percent < 90:
        return "Low Rated"
    else:
        return "Uncategorized"

# Function to check if seller is a charity store
def is_charity_seller(seller_username):
    """Check if seller is a charity store (various charity organizations)"""
    if not seller_username:
        return False
    
    seller_lower = seller_username.lower()
    
    # Common charity store names to look for
    charity_keywords = [
        "goodwill",
        "salvationarmy", 
        "salvation_army",
        "habitat", 
        "habitatrestore",
        "habitatforhumanity",
        "nonprofit",
        "svdp", 
        "stvincentdepaul", 
        "vincentdepaul",
        "catholiccharities", 
        "catholiccharity",
        "oxfam",
        "barnardos",
        "britishheartfoundation",
        "bhf",
        "redcross",
        "charity",
        "charities",
        "thriftstoreusa",
        "charitythrift",
        "nonprofitstore"
    ]
    
    return any(keyword in seller_lower for keyword in charity_keywords)

# Functions for saved searches
def save_current_search(search_params):
    """Save current search parameters"""
    search_name = f"{search_params['search_term']} in {search_params['category']} (${search_params['max_price']})"
    
    # Avoid duplicates
    existing_names = [search['name'] for search in st.session_state.saved_searches]
    if search_name not in existing_names:
        search_entry = {
            'name': search_name,
            'params': search_params,
            'saved_at': datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        }
        st.session_state.saved_searches.append(search_entry)
        return True
    return False

def load_saved_search(search_params):
    """Load saved search parameters into session state"""
    for key, value in search_params.items():
        st.session_state[f"loaded_{key}"] = value

def delete_saved_search(index):
    """Delete a saved search"""
    if 0 <= index < len(st.session_state.saved_searches):
        del st.session_state.saved_searches[index]

# Price analytics functions
def create_price_analytics(df):
    """Create price analytics dashboard"""
    if df.empty:
        return
    
    # Metrics row
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        avg_price = df['price'].mean()
        st.metric("Average Price", f"${avg_price:.2f}")
    
    with col2:
        median_price = df['price'].median()
        st.metric("Median Price", f"${median_price:.2f}")
    
    with col3:
        deal_count = len(df[df['price'] < (avg_price * 0.85)])
        st.metric("Potential Deals", f"{deal_count} item(s)", 
                 help="Items priced 15% below average")
    
    # Highlight best deals
    st.subheader("🎯 Best Deals (15% below average)")
    deals = df[df['price'] < (avg_price * 0.85)]
    if not deals.empty:
        # Convert back to formatted prices for display
        deals_display = df[df.index.isin(deals.index)].copy()
        deals_display['savings'] = deals_display.index.map(
            lambda x: f"${avg_price - df.loc[x, 'price']:.2f}"
        )
        st.dataframe(
            deals_display[['listing', 'condition', 'price', 'savings', 'seller', 'seller_rating', 'seller_feedback', 'link']],
            column_config={
                "link": st.column_config.LinkColumn("Link", display_text="View Deal"),
                "price": st.column_config.NumberColumn("price", format="$%.2f")
            },
            use_container_width=True
        )
    else:
        st.info("No significant deals found in current results.")

# UI
st.title("eBay Product Listings")
st.write("Fetch latest eBay listings by category, type, and max price.")

# Saved Searches Sidebar
with st.sidebar:
    st.header("💾 Saved Searches")
    
    if st.session_state.saved_searches:
        st.write(f"You have {len(st.session_state.saved_searches)} saved searches")
        
        for i, search in enumerate(st.session_state.saved_searches):
            with st.expander(f"🔍 {search['name'][:30]}..."):
                st.write(f"**Saved:** {search['saved_at']}")
                st.write(f"**Search:** {search['params']['search_term']}")
                st.write(f"**Category:** {search['params']['category']}")
                st.write(f"**Max Price:** ${search['params']['max_price']}")
                
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Load", key=f"load_{i}"):
                        load_saved_search(search['params'])
                        st.success("Search loaded!")
                        st.rerun()
                with col2:
                    if st.button("Delete", key=f"del_{i}"):
                        delete_saved_search(i)
                        st.success("Search deleted!")
                        st.rerun()
    else:
        st.info("No saved searches yet. Run a search and save it!")

# Main search interface
category_options = {
    "All Categories": None,
    "Action Figures & Accessories": "246",
    "Books": "267",
    "DVD & Blu-ray": "617",
    "Fragrances": "180345",
    "Furniture": "3197",
    "Hats": "52365",
    "Headphones": "112529",
    "Men's Clothing": "1059",
    "Men's Shoes": "93427",
    "Music CDs": "176984",
    "Music Cassettes": "176983",
    "Sporting Goods": "888",
    "Video Games & Consoles": "1249"
}

# Use loaded values if available, otherwise use defaults
selected_category = st.selectbox(
    "Category", 
    options=list(category_options.keys()),
    index=list(category_options.keys()).index(st.session_state.get('loaded_category', 'All Categories'))
)

listing_type_filter = st.selectbox(
    "Filter by listing type",
    ["All", "Auction", "Fixed Price", "Best Offer"],
    index=["All", "Auction", "Fixed Price", "Best Offer"].index(st.session_state.get('loaded_listing_type', 'All'))
)

# NEW: Seller Type filter
seller_type_filter = st.selectbox(
    "Seller Type",
    ["All", "Charity"],
    index=["All", "Charity"].index(st.session_state.get('loaded_seller_type', 'All')),
    help="Charity includes Goodwill, Salvation Army, Habitat for Humanity, St. Vincent de Paul, Catholic Charities, and other nonprofit thrift stores"
)


seller_rating_filter = st.multiselect(
    "Filter by seller rating (select multiple or leave empty for all)",
    ["Elite", "Excellent", "Very Good", "Good"],
    help=(
        """
        Elite: ≥5000/99% 
        Excellent: ≥1000/98% 
        Very Good: ≥500/97%
        Good: ≥100/95% 
        Average: ≥100/90% 
        Inexperienced: <100/≥90%
        Low Rated: <90%
    """
    ),
    default=st.session_state.get('loaded_seller_rating', [])
)


search_term = st.text_input(
    "Search for:", 
    value=st.session_state.get('loaded_search_term', '')
)

max_price = st.number_input(
    "Maximum total price ($):", 
    min_value=1, 
    max_value=10000, 
    value=st.session_state.get('loaded_max_price', 150)
)

limit = st.slider(
    "Number of listings to fetch:", 
    min_value=1, 
    max_value=100, 
    value=st.session_state.get('loaded_limit', 25)
)

# Search and Save buttons
col1, col2 = st.columns([3, 1])

with col1:
    search_clicked = st.button("🔍 Search eBay", type="primary")

with col2:
    if st.button("💾 Save Search"):
        search_params = {
            'search_term': search_term,
            'category': selected_category,
            'listing_type': listing_type_filter,
            'seller_rating': seller_rating_filter,
            'max_price': max_price,
            'limit': limit
        }
        
        if save_current_search(search_params):
            st.success("Search saved!")
        else:
            st.warning("Search already exists!")

# Aspect map for clothes and shoes 

aspect_map = {
    "Men's Shoes": ("US Shoe Size", "11")
}

# Execute search
if search_clicked:
    # Clear loaded values AFTER search is clicked, not before
    for key in list(st.session_state.keys()):
        if key.startswith('loaded_'):
            del st.session_state[key]

    if not access_token:
        st.error("Unable to search - missing access token")
    else:
        # Query building
        if selected_category in ["Cell Phones & Smartphones", "Tablets & eBook Readers"]:
            query = f'"{search_term}" -(case,cover,keyboard,manual,guide,screen,protector,folio,box,accessory,cable,cord,charger,pen,for parts,not working, empty box)'
        elif selected_category == "Tech Accessories":
            query = f'"{search_term}" -(broken,defective,not working,for parts, empty box)'
        else:
            query = f'"{search_term}"'

        # Build filters
        filters = [
            f"price:[1..{max_price}]",
            "priceCurrency:USD",
            "conditions:{1000|1500|2000|2500|3000}"
        ]

        if listing_type_filter == "Auction":
            filters.append("buyingOptions:{AUCTION}")
        elif listing_type_filter == "Fixed Price":
            filters.append("buyingOptions:{FIXED_PRICE}")
        elif listing_type_filter == "Best Offer":
            filters.append("buyingOptions:{BEST_OFFER}")

        # Category-specific filters for men's clothing and shoes
        if selected_category in aspect_map:
            aspect_name, aspect_value = aspect_map[selected_category]
            filters.append(f"aspect_filter={aspect_name}:{{{aspect_value}}}")

            # Also add keyword fallback for both cases
            if selected_category == "Men's Clothing":
                query += ' "Medium"'
            elif selected_category == "Men's Shoes":
                query += ' "11"'



        params = {
            "q": query,
            "filter": ",".join(filters),
            "limit": limit
        }

        category_ids = category_options[selected_category]
        if category_ids:
            params["category_ids"] = category_ids

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        with st.spinner("Searching eBay..."):
            response = requests.get("https://api.ebay.com/buy/browse/v1/item_summary/search", params=params, headers=headers)
            
            if response.status_code != 200:
                st.error(f"API Error: {response.status_code} - {response.text}")
                st.write("Debug info:")
                st.write(f"Query: {query}")
                st.write(f"Filters: {filters}")
                st.write(f"Params: {params}")
            else:
                items = response.json().get("itemSummaries", [])

                results = []
                for item in items:
                    title = item.get("title", "")
                    price = float(item.get("price", {}).get("value", 0.0))
                    shipping = float(item.get("shippingOptions", [{}])[0].get("shippingCost", {}).get("value", 0.0))
                    total_cost = price + shipping
                    link = item.get("itemWebUrl")
                    buying_options = item.get("buyingOptions", [])
                   
                    # Filter out for parts not working (condition ID: 7000)
                    condition_id = item.get("conditionId")
                    if condition_id == "7000":
                        continue
                    

                    # Get seller information
                    seller_info = item.get("seller", {})
                    seller_username = seller_info.get("username", "")
                    seller_feedback_score = seller_info.get("feedbackScore", 0)
                    seller_feedback_percent = seller_info.get("feedbackPercentage", 0)

                     # Apply seller type filter - filter results by seller username
                    if seller_type_filter == "Charity" and not is_charity_seller(seller_username):
                        continue
                    
                    # Categorize seller
                    seller_category = categorize_seller(seller_feedback_score, seller_feedback_percent)
                    
                    # Apply seller rating filter
                    if seller_rating_filter and seller_category not in seller_rating_filter:
                        continue

                    end_time_str = item.get("itemEndDate")
                    end_time = "N/A"
                    if "AUCTION" in buying_options and end_time_str:
                        try:
                            utc_dt = datetime.datetime.fromisoformat(end_time_str.replace("Z", "+00:00"))
                            central = pytz.timezone('US/Central')
                            local_dt = utc_dt.astimezone(central)
                            end_time = local_dt.strftime("%Y-%m-%d %I:%M %p %Z")
                        except Exception:
                            end_time = "Invalid date"

                    bid_count = item.get("bidCount") if "AUCTION" in buying_options else None
                    current_bid_price = float(item.get("currentBidPrice", {}).get("value", 0.0)) if "AUCTION" in buying_options else None
                    total_bid_cost = current_bid_price + shipping if current_bid_price is not None else None
                    
                    if total_cost <= max_price:
                        results.append({
                            "listing": title,
                            "condition": item.get("condition"),
                            "price": price,
                            "current_bid_price": current_bid_price,
                            "listing_type": ", ".join(buying_options),
                            "bid_count": bid_count,
                            "auction_end_time": end_time,
                            "seller": seller_username,
                            "seller_rating": seller_category,
                            "seller_feedback": seller_feedback_percent,
                            "seller_feedback_score": seller_feedback_score,
                            "link": link
                        })

                if results and listing_type_filter != "Auction":
                    df = pd.DataFrame(results)
                    df = df.sort_values(by="price").reset_index(drop=True)
                    df = df.drop(columns=['current_bid_price', 'bid_count', 'auction_end_time', 'total_bid_cost'], errors='ignore')

                    # Price Analytics Dashboard
                    st.header("📊 Price Analytics")
                    create_price_analytics(df)
                    
                    st.header("📋 Search Results")

                    # Show charity filter status if applied
                    if seller_type_filter == "Charity":
                        charity_count = len(df)
                        st.info(f"🏪 Showing {charity_count} listings from charity stores (Goodwill & Salvation Army)")
                    
                    # Format currency columns
                    def format_currency(val):
                        return f"${val:,.2f}"
                    
                    df_display = df.copy()
                    for col in ["price"]:
                        if col in df_display.columns:
                            df_display[col] = df_display[col].apply(format_currency)

                    styled_df = df_display.style.set_properties(
                        **{"text-align": "center", "white-space": "pre-wrap"}
                    ).set_table_styles([
                        {"selector": "th", "props": [("font-weight", "bold"), ("text-align", "center")]}
                    ])

                    st.dataframe(
                        styled_df,
                        column_config={
                            "link": st.column_config.LinkColumn("Link", display_text="View Listing")
                        },
                        use_container_width=True
                    )
                    
                    # Export functionality
                    csv = df.to_csv(index=False)
                    st.download_button(
                        "📥 Download Results as CSV",
                        csv,
                        f"ebay_search_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                        "text/csv"
                    )
                    
                    success_message = f"Found {len(results)} listings"
                    if seller_type_filter == "Charity":
                        success_message += " from charity stores"
                    st.success(success_message)

                elif results and listing_type_filter == "Auction": 
                    st.header("📋 Auction Listings")
                    
                    df = pd.DataFrame(results)
                    df = df.drop(columns=['price', 'total_cost'], errors='ignore')
                    df = df.sort_values(by="auction_end_time", ascending=True, na_position="last").reset_index(drop=True)

                     # Show charity filter status if applied
                    if seller_type_filter == "Charity":
                        charity_count = len(df)
                        st.info(f"🏪 Showing {charity_count} auction listings from charity stores (Goodwill & Salvation Army)")


                    # Format currency columns
                    def format_currency(val):
                        return f"${val:,.2f}"
                    
                    df_display = df.copy()
                    for col in ["price", "current_bid_price"]:
                        if col in df_display.columns:
                            df_display[col] = df_display[col].apply(format_currency)

                    styled_df = df_display.style.set_properties(
                        **{"text-align": "center", "white-space": "pre-wrap"}
                    ).set_table_styles([
                        {"selector": "th", "props": [("font-weight", "bold"), ("text-align", "center")]}
                    ])

                    st.dataframe(
                        styled_df,
                        column_config={
                            "link": st.column_config.LinkColumn("Link", display_text="View Listing")
                        },
                        use_container_width=True
                    )
                    
                    # Export functionality
                    csv = df.to_csv(index=False)
                    st.download_button(
                        "📥 Download Results as CSV",
                        csv,
                        f"ebay_search_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                        "text/csv"
                    )
                    
                    success_message = f"Found {len(results)} auction listings"
                    if seller_type_filter == "Charity":
                        success_message += " from charity stores"
                    st.success(success_message)
                    
                else:
                    no_results_message = "No listings found matching your criteria."
                    if seller_type_filter == "Charity":
                        no_results_message = "No listings found from charity stores matching your criteria."
                    st.info(no_results_message)
